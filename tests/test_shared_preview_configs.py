"""Validate the shared-service preview configurations for the supported hosts."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "integrations" / "shared"


def test_stdio_preview_config_declares_stdio_transport():
    config = json.loads((SHARED / "mcp.preview.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["qdrant-memory-shared"]
    assert server["type"] == "stdio"
    assert server["args"] == ["shared-mcp", "--url", "http://127.0.0.1:8765"]
    assert "QDRANT_MEMORY_SHARED_TOKEN" in server["env"]


def test_codex_preview_config_uses_environment_variable_names():
    config = tomllib.loads((SHARED / "codex.preview.toml").read_text(encoding="utf-8"))
    server = config["mcp_servers"]["qdrant-memory-shared"]
    assert server["args"] == ["shared-mcp", "--url", "http://127.0.0.1:8765"]
    assert server["env_vars"] == ["QDRANT_MEMORY_SHARED_TOKEN"]


def test_cordis_preview_patch_inserts_one_client_layer():
    text = (SHARED / "dsh.preview.cordis.yml").read_text(encoding="utf-8")
    assert text.count("- insert:") == 1
    assert "transport: stdio" in text
    assert "QDRANT_MEMORY_SHARED_TOKEN" in text
