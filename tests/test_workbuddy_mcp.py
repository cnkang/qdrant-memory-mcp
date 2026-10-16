"""Exercise connector stdio in synthetic profiles; GUI acceptance is separate."""

import asyncio
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_protocol import test_real_stdio_crud_restart_scope_and_redaction as exercise_scopes
from test_protocol import test_stdout_is_jsonrpc_only as exercise_stdout

pytest_plugins = ["test_protocol"]
ROOT = Path(__file__).resolve().parents[1]


def connector_launch(sandbox):
    profile, config_path, config, env, installed, cli, embeddings = sandbox
    managed = json.loads((ROOT / "integrations/workbuddy/mcp.json").read_text(encoding="utf-8"))
    server, = managed["mcpServers"].values()
    assert server["timeout"] == 30000 and server["command"] == "npx"
    alternative = json.loads((ROOT / "integrations/workbuddy/mcp.uvx.json").read_text(encoding="utf-8"))
    uvx_server, = alternative["mcpServers"].values()
    assert uvx_server["timeout"] == 30000 and uvx_server["command"] == "uvx"
    if os.environ.get("WORKBUDDY_TEST_UVX") == "1":
        # The uvx distribution stays the documented alternative custom MCP
        # route. It launches the exact public PyPI pin with no personal
        # profile or credentials.
        uvx = shutil.which(uvx_server["command"])
        assert uvx, "Connector launch requested but uvx is not installed"
        launch = [uvx, *uvx_server["args"][:-1]]
        env["UV_PYTHON"] = str(Path(installed[0]).parent / ("python.exe" if os.name == "nt" else "python"))
        result = subprocess.run([*launch, "--help"], env=env, capture_output=True, timeout=180)
        assert result.returncode == 0
    else:
        launch = installed  # Fresh wheel/sdist environment matrix tests Runtime.
    return profile, config_path, config, env, launch, cli, embeddings


def test_connector_crud_restart_scope_writerlease_and_redaction(sandbox):
    exercise_scopes(connector_launch(sandbox))


def test_connector_stdout_protocol_only(sandbox):
    exercise_stdout(connector_launch(sandbox))


def test_connector_default_profile(sandbox):
    profile, _, _, env, launch, _, _ = connector_launch(sandbox)
    profile.rename(profile.parent / ".qdrant-memory")

    async def check():
        params = StdioServerParameters(command=launch[0], args=[*launch[1:], "mcp"], env=env)
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                assert len((await session.list_tools()).tools) == 4
                result = await asyncio.wait_for(session.call_tool("qdrant_memory_search", {"query": "synthetic private text"}), timeout=30)
                assert not result.model_dump(by_alias=True)["isError"]
                assert json.loads(result.content[0].text)["memories"] == []
    asyncio.run(check())


def test_connector_missing_embedding_startup_redacts_credentials(sandbox):
    profile, config_path, config, env, launch, _, _ = connector_launch(sandbox)
    config["embedding"]["base_url"] = "http://127.0.0.1:1"
    config["embedding"]["api_key"] = "synthetic-secret-no-real-credential"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run([*launch, "--home", str(profile), "mcp"], input="", text=True, env=env, capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "synthetic-secret" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


def test_connector_invalid_profile_startup_fails_safely(sandbox):
    profile, config_path, _, env, launch, _, _ = connector_launch(sandbox)
    config_path.write_text('{"embedding": "synthetic-sensitive-config"}', encoding="utf-8")
    result = subprocess.run([*launch, "--home", str(profile), "mcp"], input="", text=True, env=env, capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "synthetic-sensitive-config" not in result.stdout + result.stderr


def test_connector_invalid_embedding_key_fails_safely(sandbox):
    profile, config_path, config, env, launch, _, _ = connector_launch(sandbox)

    class Unauthorized(BaseHTTPRequestHandler):
        calls = 0

        def do_POST(self):
            type(self).calls += 1
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"synthetic-secret-denied"}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Unauthorized)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config["embedding"]["base_url"] = f"http://127.0.0.1:{server.server_port}"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        env["EMBEDDING_API_KEY"] = "synthetic-secret-no-real-credential"
        result = subprocess.run([*launch, "--home", str(profile), "mcp"], input="", text=True, env=env, capture_output=True, timeout=30)
        assert result.returncode != 0 and Unauthorized.calls > 0
        assert "synthetic-secret" not in result.stdout + result.stderr
        assert "Traceback" not in result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
