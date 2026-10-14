"""Preview candidates must not race the protected first PyPI publication."""

import importlib.util
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location("workbuddy_public", ROOT / "integrations/workbuddy/public_install.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_unpublished_candidate_reports_unverified(monkeypatch):
    check = module()
    monkeypatch.setattr(check, "release", lambda *a: None)
    assert check.available(ROOT) is False


def test_matching_public_version_runs_public_gate(monkeypatch):
    check = module()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    monkeypatch.setattr(check, "release", lambda *a: {"info": {"name": project["name"], "version": project["version"], "requires_dist": project["dependencies"], "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
    assert check.available(ROOT) is True


def test_conflicting_public_runtime_fails_closed(monkeypatch):
    check = module()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    monkeypatch.setattr(check, "release", lambda *a: {"info": {"name": project["name"], "version": project["version"], "requires_dist": ["hermes-plugin-qdrant-memory[mcp]==9.9.9"], "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
    with pytest.raises(ValueError, match="public"):
        check.available(ROOT)


def test_tag_build_leaves_public_acceptance_to_protected_publisher():
    workflow = (ROOT / ".github/workflows/workbuddy-release.yml").read_text(encoding="utf-8")
    assert "WORKBUDDY_TEST_UVX" not in workflow
    publisher = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "DIST_TEST_UVX=1" in publisher
    assert "environment: pypi" in publisher and "environment: mcp-registry" in publisher
