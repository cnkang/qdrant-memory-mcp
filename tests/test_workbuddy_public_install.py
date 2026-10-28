"""Preview candidates must not race the protected first PyPI publication."""

import importlib.util
import tomllib
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mirror_root(tmp_path):
    """Exercise legacy mirror validation independently of production metadata."""
    import json
    (tmp_path / "launcher-source.json").write_text((ROOT / "launcher-source.json").read_text())
    folder = tmp_path / "integrations/workbuddy"
    folder.mkdir(parents=True)
    mcp = json.loads((ROOT / "integrations/workbuddy/mcp.json").read_text())
    mcp["mcpServers"]["qdrant-memory"]["npmRegistries"].append("https://registry.npmmirror.com")
    (folder / "mcp.json").write_text(json.dumps(mcp))
    return tmp_path


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


def test_declared_dev_extras_do_not_conflict(monkeypatch):
    check = module()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    published = list(project["dependencies"]) + [
        "pytest<10,>=8; extra == \"dev\"",
        "requests<3,>=2; extra == \"dev\"",
    ]
    monkeypatch.setattr(check, "release", lambda *a: {"info": {"name": project["name"], "version": project["version"], "requires_dist": published, "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
    assert check.available(ROOT) is True


def test_undeclared_extra_gated_requirement_fails_closed(monkeypatch):
    check = module()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    published = list(project["dependencies"]) + ['undici==9.9.9; extra == "dev"']
    monkeypatch.setattr(check, "release", lambda *a: {"info": {"name": project["name"], "version": project["version"], "requires_dist": published, "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
    with pytest.raises(ValueError, match="public"):
        check.available(ROOT)


def test_extra_gated_requirement_must_match_its_own_extra(monkeypatch, tmp_path):
    check = module()
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "qdrant-memory-mcp"
version = "0.2.5"
dependencies = ["runtime==1.0"]

[project.optional-dependencies]
dev = ["pytest>=8"]
docs = ["sphinx>=7"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    info = {
        "name": "qdrant-memory-mcp",
        "version": "0.2.5",
        "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->",
    }

    def publish(*requires):
        monkeypatch.setattr(
            check,
            "release",
            lambda *a: {"info": {**info, "requires_dist": list(requires)}},
        )

    publish("runtime==1.0", 'sphinx>=7; extra == "docs"')
    assert check.available(tmp_path) is True
    publish("runtime==1.0", 'sphinx>=7; extra == "dev"')
    with pytest.raises(ValueError, match="public"):
        check.available(tmp_path)
    # A partial list stays valid when every gated entry belongs to its own extra.
    publish("runtime==1.0", 'pytest>=8; extra == "dev"')
    assert check.available(tmp_path) is True


def test_undeclared_unconditional_requirement_fails_closed(monkeypatch):
    check = module()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    published = list(project["dependencies"]) + ["undici==9.9.9", "evil-extra==1.0"]
    monkeypatch.setattr(check, "release", lambda *a: {"info": {"name": project["name"], "version": project["version"], "requires_dist": published, "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
    with pytest.raises(ValueError, match="public"):
        check.available(ROOT)


def test_markers_outside_a_declared_extra_fail_closed(monkeypatch):
    check = module()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    entries = [
        'pytest<10,>=8; extra == "prod"',
        'pytest<10,>=8; extra == "dev" or python_version < "3.11"',
        'pytest<10,>=8; extra != "dev"',
    ]
    for entry in entries:
        published = list(project["dependencies"]) + [entry]
        monkeypatch.setattr(check, "release", lambda *a, published=published: {"info": {"name": project["name"], "version": project["version"], "requires_dist": published, "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
        with pytest.raises(ValueError, match="public"):
            check.available(ROOT)
    # A conjunct inside the declared extra stays gated.
    gated = list(project["dependencies"]) + [
        'pytest<10,>=8; extra == "dev" and python_version < "3.12"'
    ]
    monkeypatch.setattr(check, "release", lambda *a: {"info": {"name": project["name"], "version": project["version"], "requires_dist": gated, "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"}})
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


def test_launcher_mirror_conflict_fails_closed(monkeypatch, mirror_root):
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
    assert check.launcher(mirror_root) is True

    def conflicting(url, *a, **k):
        return Response(bad if urllib.parse.urlparse(url).hostname == "registry.npmmirror.com" else good)

    monkeypatch.setattr(check.urllib.request, "urlopen", conflicting)
    with pytest.raises(ValueError, match="npmmirror"):
        check.launcher(mirror_root)


def test_launcher_mirror_absence_is_informational(monkeypatch, capsys, mirror_root):
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

    def selective(url, *args, **kwargs):
        if urllib.parse.urlparse(url).hostname == "registry.npmmirror.com":
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return Response()

    monkeypatch.setattr(check.urllib.request, "urlopen", selective)
    assert check.launcher(mirror_root) is True
    assert "does not serve the pinned version" in capsys.readouterr().out


def test_launcher_first_registry_must_be_canonical(tmp_path):
    import json as jsonlib
    check = module()
    pin = (ROOT / "launcher-source.json").read_text(encoding="utf-8")
    mcp = jsonlib.loads((ROOT / "integrations/workbuddy/mcp.json").read_text(encoding="utf-8"))
    servers = mcp["mcpServers"]["qdrant-memory"]
    servers["npmRegistries"] = ["https://registry.npmmirror.com", "https://registry.npmjs.org"]
    (tmp_path / "launcher-source.json").write_text(pin)
    (tmp_path / "integrations/workbuddy").mkdir(parents=True)
    (tmp_path / "integrations/workbuddy/mcp.json").write_text(jsonlib.dumps(mcp))
    with pytest.raises(ValueError, match="canonical registry"):
        check.launcher(tmp_path)


def test_launcher_mirror_version_without_canonical_fails_closed(monkeypatch, mirror_root):
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

    def selective(url, *args, **kwargs):
        if urllib.parse.urlparse(url).hostname == "registry.npmjs.org":
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return Response()

    monkeypatch.setattr(check.urllib.request, "urlopen", selective)
    with pytest.raises(ValueError, match="does not publish"):
        check.launcher(mirror_root)


def test_launcher_unreachable_mirror_is_informational(monkeypatch, capsys, mirror_root):
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

    def selective(url, *args, **kwargs):
        if urllib.parse.urlparse(url).hostname == "registry.npmmirror.com":
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)
        return Response()

    monkeypatch.setattr(check.urllib.request, "urlopen", selective)
    assert check.launcher(mirror_root) is True
    assert "unreachable" in capsys.readouterr().out


def test_release_workflow_requires_the_public_launcher_pin():
    workflow = (ROOT / ".github/workflows/workbuddy-release.yml").read_text(encoding="utf-8")
    assert "public_install.py --require-launcher" in workflow
    preview = (ROOT / ".github/workflows/workbuddy-preview.yml").read_text(encoding="utf-8")
    assert "public-launcher-acceptance.mjs" in preview
