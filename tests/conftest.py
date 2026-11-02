"""Share the disposable installed-runtime sandbox across harness modules."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.fixture
def sandbox(tmp_path):
    """Provide disposable storage, synthetic embeddings and guarded installed launchers."""

    class Embeddings(BaseHTTPRequestHandler):
        """Serve deterministic vectors and controlled failures over local HTTP."""

        failures = 0

        def do_POST(self):
            """Return aligned vectors or an injected retryable embedding failure."""
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if (
                any(text.startswith("doc:recover-fixture") for text in body["input"])
                and self.failures
            ):
                type(self).failures -= 1
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            vectors = [
                [1.0, 0.0, 0.0]
                if "similarity-fixture:" in text
                else [
                    v / 255 + 0.01 for v in hashlib.sha256(text.encode()).digest()[:3]
                ]
                for text in body["input"]
            ]
            payload = json.dumps({"embeddings": vectors}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            """Suppress fixture HTTP logs so tests never mix them into protocol output."""
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Embeddings)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "profile"
    profile.mkdir()
    config = {
        "scope": {"user_id": "test-user", "agent_id": "test-agent"},
        "embedding": {
            "dimensions": 3,
            "model": "fixture",
            "base_url": f"http://127.0.0.1:{server.server_port}",
            "document_instruction": "doc:",
        },
        "write": {
            "max_attempts": 2,
            "backoff_base_seconds": 0,
            "backoff_max_seconds": 0,
        },
    }
    config_path = profile / "qdrant-memory.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import sys\nclass NoHermes:\n def find_spec(self, fullname, path=None, target=None):\n  if fullname.split('.')[0] in {'agent', 'hermes_constants', 'hermes_cli'}: raise RuntimeError('Hermes dependency forbidden')\nsys.meta_path.insert(0, NoHermes())\n",
        encoding="utf-8",
    )
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),
        PYTHONPATH=str(guard),
        HERMES_HOME=str(tmp_path / "unused-hermes"),
    )
    # Resolve the installed console script through sysconfig: on Windows the
    # scripts live in a Scripts/ subdirectory, unlike POSIX prefixes.
    script = Path(sysconfig.get_path("scripts")) / (
        "qdrant-memory-mcp.exe" if sys.platform == "win32" else "qdrant-memory-mcp"
    )
    launch = [str(script)]
    runtime_wheels = os.environ.get("DIST_TEST_UVX_RUNTIME_WHEELS")
    if runtime_wheels or os.environ.get("DIST_TEST_UVX"):
        uvx = shutil.which("uvx")
        assert uvx, "uvx acceptance was requested but uvx is unavailable"
        launch = [uvx, "--from", "qdrant-memory-mcp==0.2.4"]
        if runtime_wheels:
            launch += [
                "--find-links",
                str(Path(__file__).resolve().parents[1] / "dist"),
                "--find-links",
                runtime_wheels,
            ]
        launch += ["qdrant-memory-mcp"]
        env["UV_CACHE_DIR"] = str(tmp_path / "uv-cache")
        env["UV_PYTHON"] = sys.executable

    def cli(*args, ok=True):
        """Run the installed launcher in the synthetic profile and check JSON status."""
        result = subprocess.run(
            [*launch, "--home", str(profile), *args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert (result.returncode == 0) == ok, result.stderr
        return json.loads(result.stdout)

    cli("init")
    yield profile, config_path, config, env, launch, cli, Embeddings
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
