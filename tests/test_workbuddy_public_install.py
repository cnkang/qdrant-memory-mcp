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


def test_launcher_pin_reports_unverified_when_unpublished(monkeypatch):
    import urllib.error
    check = module()
    def missing(*args, **kwargs):
        raise urllib.error.HTTPError("https://registry.npmjs.org/x", 404, "Not Found", None, None)
    monkeypatch.setattr(check.urllib.request, "urlopen", missing)
    assert check.launcher(ROOT) is False


def test_launcher_pin_requires_matching_published_integrity(monkeypatch):
    import json as jsonlib
    check = module()
    pin = jsonlib.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))
    payload = {"name": pin["name"], "version": pin["version"], "dist": {"integrity": pin["integrity"]}}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return jsonlib.dumps(payload).encode()

    monkeypatch.setattr(check.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert check.launcher(ROOT) is True
    payload["dist"]["integrity"] = "sha512-" + "B" * 86 + "=="
    with pytest.raises(ValueError, match="integrity"):
        check.launcher(ROOT)
    payload["dist"]["integrity"] = pin["integrity"]
    payload["version"] = "9.9.9"
    with pytest.raises(ValueError, match="identity"):
        check.launcher(ROOT)


def test_launcher_mirror_conflict_fails_closed(monkeypatch):
    import json as jsonlib
    check = module()
    pin = jsonlib.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))

    class Response:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return jsonlib.dumps(self.payload).encode()

    good = {"name": pin["name"], "version": pin["version"], "dist": {"integrity": pin["integrity"]}}
    bad = {"name": pin["name"], "version": pin["version"], "dist": {"integrity": "sha512-" + "C" * 86 + "=="}}

    monkeypatch.setattr(check.urllib.request, "urlopen", lambda *a, **k: Response(good))
    assert check.launcher(ROOT) is True

    monkeypatch.setattr(check.urllib.request, "urlopen", lambda url, *a, **k: Response(bad if "npmmirror" in url else good))
    with pytest.raises(ValueError, match="npmmirror"):
        check.launcher(ROOT)


def test_launcher_mirror_absence_is_informational(monkeypatch, capsys):
    import json as jsonlib
    import urllib.error
    check = module()
    pin = jsonlib.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))
    payload = {"name": pin["name"], "version": pin["version"], "dist": {"integrity": pin["integrity"]}}

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return jsonlib.dumps(payload).encode()

    def selective(url, *args, **kwargs):
        if "npmmirror" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return Response()

    monkeypatch.setattr(check.urllib.request, "urlopen", selective)
    assert check.launcher(ROOT) is True
    assert "does not serve the pinned version" in capsys.readouterr().out


def test_release_workflow_requires_the_public_launcher_pin():
    workflow = (ROOT / ".github/workflows/workbuddy-release.yml").read_text(encoding="utf-8")
    assert "public_install.py --require-launcher" in workflow
    preview = (ROOT / ".github/workflows/workbuddy-preview.yml").read_text(encoding="utf-8")
    assert "public-launcher-acceptance.mjs" in preview
