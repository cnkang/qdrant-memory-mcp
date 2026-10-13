"""Check immutable publication retries reject conflicting public metadata."""

import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_retry_accepts_exact_active_metadata(monkeypatch):
    module = load_script("registry_publish")
    server = json.loads((ROOT / "server.json").read_text())
    remote = {"server": server, "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}}
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(remote).encode()))
    assert module.published(server)
    remote["server"] = {**server, "version": "9.9.9"}
    with pytest.raises(AssertionError, match="Conflicting Registry"):
        module.published(server)
    remote["server"] = server
    remote["_meta"]["io.modelcontextprotocol.registry/official"]["status"] = "deleted"
    with pytest.raises(AssertionError):
        module.published(server)


def test_registry_retry_only_treats_404_as_absent(monkeypatch):
    module = load_script("registry_publish")

    def unavailable(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.invalid", 404, "absent", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", unavailable)
    assert module.published({"name": "io.github.cnkang/qdrant-memory", "version": "0.1.0"}) is False

    def forbidden(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.invalid", 403, "forbidden", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
    with pytest.raises(urllib.error.HTTPError):
        module.published({"name": "io.github.cnkang/qdrant-memory", "version": "0.1.0"})


def test_registry_metadata_survives_official_optional_boolean_omission(monkeypatch):
    module = load_script("registry_publish")
    server = json.loads((ROOT / "server.json").read_text())

    def official_serialization(value):
        if isinstance(value, dict):
            return {key: official_serialization(item) for key, item in value.items()
                    if not (key in {"isRequired", "isSecret", "isRepeated"} and item is False)}
        if isinstance(value, list):
            return [official_serialization(item) for item in value]
        return value

    remote = {"server": official_serialization(server), "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}}
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(remote).encode()))
    assert module.published(server)


def test_pypi_retry_rejects_wrong_runtime_before_download(monkeypatch, tmp_path):
    module = load_script("pypi_release")
    (tmp_path / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "release", lambda *a: {"info": {
        "name": "qdrant-memory-mcp", "version": "0.1.0",
        "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->",
        "requires_dist": ["hermes-plugin-qdrant-memory[mcp]==0.1.0"],
    }})
    monkeypatch.setattr(module, "__name__", "test")
    monkeypatch.setattr(module.os.sys, "argv", ["pypi_release.py", "--download"])
    with pytest.raises(AssertionError):
        module.main()
