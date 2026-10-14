"""Exercise installed console scripts over stdio using only disposable services."""

import asyncio
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
    script = Path(sys.executable).parent / (
        "qdrant-memory-mcp.exe" if sys.platform == "win32" else "qdrant-memory-mcp"
    )
    launch = [str(script)]
    runtime_wheels = os.environ.get("DIST_TEST_UVX_RUNTIME_WHEELS")
    if runtime_wheels or os.environ.get("DIST_TEST_UVX"):
        uvx = shutil.which("uvx")
        assert uvx, "uvx acceptance was requested but uvx is unavailable"
        launch = [uvx, "--from", "qdrant-memory-mcp==0.1.2"]
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


def test_real_stdio_crud_restart_scope_and_redaction(sandbox):
    """Exercise real SDK CRUD, scope denial, writer exclusion and restart persistence."""
    profile, config_path, config, env, script, cli, _ = sandbox
    foreign = []
    for user, agent in [("other-user", "test-agent"), ("test-user", "other-agent")]:
        config["scope"] = {"user_id": user, "agent_id": agent}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        foreign.append(cli("add", "--text", f"private-{user}-{agent}")["id"])
    config["scope"] = {"user_id": "test-user", "agent_id": "test-agent"}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    async def connection(callback):
        """Open a real stdio SDK session and execute one acceptance phase."""
        parameters = StdioServerParameters(
            command=script[0],
            args=[*script[1:], "--home", str(profile), "mcp"],
            env=env,
            cwd=str(profile.parent),
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await callback(session)

    async def call(session, tool, arguments, ok=True):
        """Decode a scoped tool result and reject sensitive data in errors."""
        result = await session.call_tool("qdrant_memory_" + tool, arguments)
        assert result.model_dump(by_alias=True)["isError"] is not ok
        encoded = result.content[0].text
        if not ok:
            assert all(
                secret not in encoded
                for secret in [
                    "sensitive-fixture-value",
                    "Traceback",
                    "private-other-user",
                    "private-test-user-other-agent",
                ]
            )
        return json.loads(encoded)

    async def first(session):
        """Check tool schemas, CRUD authorization and competing writer refusal."""
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} == {
            "qdrant_memory_search",
            "qdrant_memory_add",
            "qdrant_memory_update",
            "qdrant_memory_delete",
        }
        assert all(t.model_dump(by_alias=True)["inputSchema"]["additionalProperties"] is False for t in tools)
        added = await call(session, "add", {"text": "distribution durable fact"})
        memory_id = added["id"]
        found = await call(session, "search", {"query": "distribution durable fact"})
        assert memory_id in {m["id"] for m in found["memories"]}
        assert not set(foreign) & {m["id"] for m in found["memories"]}
        await call(session, "update", {"id": memory_id, "text": "updated durable fact"})
        for memory in foreign:
            await call(
                session,
                "update",
                {"id": memory, "text": "sensitive-fixture-value"},
                ok=False,
            )
            await call(session, "delete", {"id": memory}, ok=False)
        await call(
            session,
            "add",
            {"text": "sensitive-fixture-value", "user_id": "other-user"},
            ok=False,
        )
        await call(
            session, "add", {"text": {"api_key": "sensitive-fixture-value"}}, ok=False
        )
        busy = cli("add", "--text", "busy", ok=False)
        assert busy["error"]["type"] == "WriterBusyError"
        return memory_id

    memory_id = asyncio.run(connection(first))

    async def restarted(session):
        """Verify the replacement survives restart before deleting its exact ID."""
        found = await call(session, "search", {"query": "updated durable fact"})
        matches = [m for m in found["memories"] if m["id"] == memory_id]
        assert len(matches) == 1 and matches[0]["text"] == "updated durable fact"
        await call(session, "delete", {"id": memory_id})

    asyncio.run(connection(restarted))

    async def deleted(session):
        """Verify a deleted memory remains absent on a subsequent server restart."""
        found = await call(session, "search", {"query": "updated durable fact"})
        assert not found["memories"]

    asyncio.run(connection(deleted))


def test_similar_explicit_facts_survive_sdk_calls_and_restart(sandbox):
    """Retain distinct cosine-identical facts and deduplicate exact text across restart."""
    profile, _, _, env, script, cli, _ = sandbox

    async def check():
        """Save both similar facts through the SDK and verify canonical duplicate handling."""
        params = StdioServerParameters(
            command=script[0],
            args=[*script[1:], "--home", str(profile), "mcp"],
            env=env,
        )
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                ids = []
                for text in (
                    "similarity-fixture: cats preferred",
                    "similarity-fixture: cats avoided",
                ):
                    result = await session.call_tool(
                        "qdrant_memory_add", {"text": text}
                    )
                    assert not result.model_dump(by_alias=True)["isError"], result.content
                    value = json.loads(result.content[0].text)
                    assert value["action"] == "ADD"
                    ids.append(value["id"])
                result = await session.call_tool(
                    "qdrant_memory_add", {"text": "similarity-fixture: cats preferred"}
                )
                assert json.loads(result.content[0].text) == {
                    "action": "SKIP",
                    "id": ids[0],
                }
                assert len(set(ids)) == 2
                return set(ids)

    ids = asyncio.run(check())
    assert {
        m["id"]
        for m in cli("search", "--query", "similarity-fixture: cats")["memories"]
    } == ids


def test_stdout_is_jsonrpc_only(sandbox):
    """Require stdout to contain only the expected JSON-RPC responses."""
    profile, _, _, env, script, _, _ = sandbox
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "distribution-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    process = subprocess.Popen(
        [*script, "--home", str(profile), "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=profile.parent,
    )
    received = queue.Queue()

    def read_stdout():
        """Collect server protocol lines without blocking the parent test."""
        for line in process.stdout:
            received.put(line)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    try:
        process.stdin.write(json.dumps(messages[0]) + "\n")
        process.stdin.flush()
        initialized = json.loads(received.get(timeout=90))
        assert (
            initialized["id"] == 1
            and initialized["jsonrpc"] == "2.0"
            and "result" in initialized
        )
        process.stdin.write("".join(json.dumps(m) + "\n" for m in messages[1:]))
        process.stdin.flush()
        listed = json.loads(received.get(timeout=30))
        assert listed["id"] == 2 and listed["jsonrpc"] == "2.0" and "result" in listed
        assert len(listed["result"]["tools"]) == 4
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        reader.join(timeout=5)
    assert process.returncode == 0, process.stderr.read()
    assert not reader.is_alive() and received.empty(), (
        "Unexpected stdout after protocol responses"
    )
    process.stdout.close()
    process.stderr.close()


def test_failed_write_recovers_through_mcp_after_restart(sandbox):
    """Recover a terminal failed write through the supported operator retry flow."""
    profile, _, _, env, script, cli, embeddings = sandbox

    async def run(failing):
        """Inject a tool write failure or verify its durable recovery after restart."""
        parameters = StdioServerParameters(
            command=script[0],
            args=[*script[1:], "--home", str(profile), "mcp"],
            env=env,
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if failing:
                    embeddings.failures = 10
                    result = await session.call_tool(
                        "qdrant_memory_add", {"text": "recover-fixture durable fact"}
                    )
                    assert result.model_dump(by_alias=True)["isError"]
                else:
                    found = await session.call_tool(
                        "qdrant_memory_search",
                        {"query": "recover-fixture durable fact"},
                    )
                    assert not found.model_dump(by_alias=True)["isError"]
                    memories = json.loads(found.content[0].text)["memories"]
                    assert (
                        len(memories) == 1
                        and memories[0]["text"] == "recover-fixture durable fact"
                    )

    asyncio.run(run(True))
    embeddings.failures = 0
    # Terminal FAILED operations use the existing trusted operator retry flow.
    # Never rewrite ledger rows or invoke private Runtime methods in acceptance.
    cli("retry")
    asyncio.run(run(False))
