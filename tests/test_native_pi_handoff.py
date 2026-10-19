"""Real Hermes and Pi lifecycle handoff through one Owner and verified HTTPS MCP."""

import os
import sys
from pathlib import Path

import pytest


def test_native_hermes_to_pi_authorized_project_handoff(tmp_path, monkeypatch):
    """Use actual Host callbacks with deterministic model/embedding fixtures."""
    root = os.environ.get("QDRANT_OWNER_RUNTIME_ROOT")
    if not root:
        pytest.skip(
            "Requires explicitly selected unreleased Owner Runtime and real Hermes checkout"
        )
    import hashlib
    import json
    import socket
    import subprocess
    import threading
    import time
    from types import SimpleNamespace

    import uvicorn

    sys.path.insert(0, str(Path(root).resolve()))
    from agent.memory_manager import MemoryManager
    from qdrant_memory.provider import QdrantMemoryProvider
    from qdrant_memory.remote_gateway import create_gateway
    from tests.helpers import Embedder, LLM, config

    tokens = {
        name: hashlib.sha256(("host-fixture-" + name).encode()).hexdigest()
        for name in ("native", "project", "reader")
    }
    clients = [
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "principal": name,
            "owner_id": "hermes-user",
            "device_id": name,
            "logical_agent_id": "pi" if name == "reader" else "hermes",
            "space_id": "private" if name == "native" else "alpha",
            "visibility": "private" if name == "native" else "project",
            "permission": "read" if name == "reader" else "write",
        }
        for name, token in tokens.items()
    ]
    clients[1]["capture_rule_id"] = "synthetic-user-approved-alpha"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"clients": clients}), encoding="utf-8")
    policy.chmod(0o600)
    for name, token in tokens.items():
        monkeypatch.setenv("QM_" + name.upper(), token)
    cfg = config(
        native_owner={
            "enabled": True,
            "policy": str(policy),
            "port": 0,
            "private_token_env": "QM_NATIVE",
            "shared_capture_token_envs": ["QM_PROJECT"],
        }
    )
    native = QdrantMemoryProvider(
        plugin_context=SimpleNamespace(llm=LLM()), embedder=Embedder(), overrides=cfg
    )
    native.initialize("session-a", hermes_home=str(tmp_path))
    manager = MemoryManager()
    manager.add_provider(native)
    service, thread = None, None
    try:
        native.on_turn_start(1, "Project Alpha uses SQLite WAL.")
        manager.sync_all(
            "Project Alpha uses SQLite WAL.", "ack", session_id="session-a"
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            native.wait_idle(0.1)
            if native.store.count() >= 2:
                break
            time.sleep(0.01)
        else:
            pytest.fail(
                "Hermes lifecycle did not save authorized private/project records"
            )
        cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=127.0.0.1",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(64)
            port = sock.getsockname()[1]
            app = create_gateway(
                native._native_owner.owner, allowed_hosts=[f"127.0.0.1:{port}"]
            )
            service = uvicorn.Server(
                uvicorn.Config(
                    app,
                    ssl_certfile=str(cert),
                    ssl_keyfile=str(key),
                    proxy_headers=False,
                    access_log=False,
                    log_level="critical",
                )
            )
            thread = threading.Thread(target=service.run, kwargs={"sockets": [sock]})
            thread.start()
            while not service.started and time.monotonic() < deadline:
                time.sleep(0.01)
            assert service.started
            env = {
                **os.environ,
                "QM_REAL_OWNER": "1",
                "QDRANT_MEMORY_OWNER_URL": f"https://127.0.0.1:{port}/mcp",
                "QDRANT_MEMORY_RUNTIME_PYTHON": sys.executable,
                "QDRANT_MEMORY_CA_FILE": str(cert),
                "QDRANT_MEMORY_REMOTE_TOKEN": tokens["reader"],
                "PYTHONPATH": str(Path(root).resolve())
                + os.pathsep
                + os.environ.get("PYTHONPATH", ""),
            }
            try:
                result = subprocess.run(
                    ["node", "--test", "tests/test_pi_owner_host.mjs"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                assert result.returncode == 0, result.stdout + result.stderr
            finally:
                service.should_exit = True
                thread.join(timeout=30)
                assert not thread.is_alive()
    finally:
        if service is not None:
            service.should_exit = True
        if thread is not None:
            thread.join(timeout=30)
            assert not thread.is_alive()
        manager.shutdown_all()
