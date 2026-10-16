"""Guard connector inputs, deterministic bytes and immutable output files."""

import importlib.util
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def builder():
    spec = importlib.util.spec_from_file_location("connector_build", ROOT / "integrations/workbuddy/build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_connector_metadata_and_generated_pin():
    module = builder()
    meta, mcp, source, project, runtime = module.inputs(ROOT)
    assert meta["minWorkbuddyVersion"] == "4.24.0"
    assert meta["type"] == "mcp"
    assert len(meta["examples_en"]) == len(meta["examples_zh"]) == 4
    server, = mcp["mcpServers"].values()
    assert server == {"type": "stdio", "command": "uvx", "args": ["--from", f"qdrant-memory-mcp=={project['version']}", "qdrant-memory-mcp", "mcp"], "timeout": 30000}
    assert runtime["version"] == "0.3.0"
    assert len(source["commit"]) == 40


@pytest.mark.parametrize("name", ["/etc/passwd", "../secret", "qdrant-memory/../secret", "qdrant-memory/.env", "qdrant-memory/data.db", "qdrant-memory/scripts/secret.py", "qdrant-memory\\SKILL.md"])
def test_unsafe_resource_rejected(name):
    assert not builder().safe_resource(name)


def test_archive_determinism_and_safe_writes(tmp_path):
    module = builder()
    files = {"qdrant-memory-workbuddy/icon.svg": (b"svg", 0o644)}
    data = module.archive_bytes(files)
    assert data == module.archive_bytes(dict(reversed(list(files.items()))))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == list(files)
        assert archive.infolist()[0].date_time == (1980, 1, 1, 0, 0, 0)
    path = tmp_path / "archive.zip"
    module.write_once(path, data)
    module.write_once(path, data)
    with pytest.raises(ValueError, match="overwrite"):
        module.write_once(path, b"different")
    if hasattr(Path, "symlink_to"):
        link = tmp_path / "link"
        try:
            link.symlink_to(path)
        except OSError:
            return  # Windows may lack the symlink privilege.
        with pytest.raises(ValueError, match="symlink"):
            module.write_once(link, data)


@pytest.mark.parametrize("field,value", [("source", "Bad ID"), ("version", "01.0.0"), ("minWorkbuddyVersion", "4.23.0"), ("examples_en", ["one"]), ("type", "cli"), ("auth_mode", "token")])
def test_invalid_metadata_fails_closed(tmp_path, monkeypatch, field, value):
    read = Path.read_text
    def legacy_windows_read(path, *args, **kwargs):
        kwargs.setdefault("encoding", "cp1252")
        return read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", legacy_windows_read)
    module = builder()
    meta = json.loads((ROOT / "integrations/workbuddy/connector-meta.json").read_text(encoding="utf-8"))
    meta[field] = value
    with pytest.raises(ValueError):
        module.validate_metadata(meta)


def test_release_tag_must_match_current_package():
    module = builder()
    with pytest.raises(ValueError, match="tag"):
        module.package_name("0.1.0", "0.1.2", "v0.1.4")
    assert module.package_name("0.1.0", "0.1.2", None).endswith("-preview.zip")


def test_multiple_servers_and_python_runtime_rejected():
    module = builder()
    valid = module.inputs(ROOT)[1]
    valid["mcpServers"]["extra"] = next(iter(valid["mcpServers"].values()))
    with pytest.raises(ValueError):
        module.validate_mcp(valid, "0.1.2")


def test_skill_source_checkout_identity_and_dirty_tree(tmp_path):
    module = builder()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (tmp_path / "resource.md").write_text("reviewed", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "fixture")
    git("remote", "add", "origin", "https://github.com/cnkang/skills.git")
    source = {"repository": "https://github.com/cnkang/skills.git", "commit": git("rev-parse", "HEAD"), "version": "0.2.5"}
    module.validate_skill_source(tmp_path, source)
    git("remote", "set-url", "origin", "https://github.com/cnkang/skills")
    module.validate_skill_source(tmp_path, source)
    with pytest.raises(ValueError, match="pinned commit"):
        module.validate_skill_source(tmp_path, {**source, "commit": "0" * 40})
    git("remote", "set-url", "origin", "https://example.invalid/skills.git")
    with pytest.raises(ValueError, match="origin"):
        module.validate_skill_source(tmp_path, source)
    git("remote", "set-url", "origin", source["repository"])
    (tmp_path / "resource.md").write_text("unreviewed", encoding="utf-8")
    with pytest.raises(ValueError, match="clean"):
        module.validate_skill_source(tmp_path, source)


def test_package_manifest_provenance_and_output_guard(tmp_path, monkeypatch):
    module = builder()
    monkeypatch.setattr(module, "skill_files", lambda *a: {"skills/qdrant-memory/SKILL.md": (b"generated", 0o644), "skills/qdrant-memory/LICENSE": (b"MIT", 0o644)})
    paths = module.build(ROOT, tmp_path, tmp_path / "one")
    again = module.build(ROOT, tmp_path, tmp_path / "two")
    assert [p.read_bytes() for p in paths] == [p.read_bytes() for p in again]
    with zipfile.ZipFile(paths[0]) as archive:
        assert all(n.startswith("qdrant-memory-workbuddy/") for n in archive.namelist())
        provenance = json.loads(archive.read("qdrant-memory-workbuddy/provenance.json"))
        assert provenance["skill_commit"] == module.inputs(ROOT)[2]["commit"]
        assert provenance["release_tag"] is None
        assert len(json.loads(archive.read("qdrant-memory-workbuddy/mcp.json"))["mcpServers"]) == 1
    with pytest.raises(ValueError, match="dist/workbuddy"):
        module.build(ROOT, tmp_path, ROOT / "unapproved-generated-skill")


def test_workflow_skill_pins_and_readonly_preview():
    source = builder().inputs(ROOT)[2]
    for name in ("workbuddy-preview.yml", "workbuddy-release.yml"):
        workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "ref: " + source["commit"] in workflow
        assert "persist-credentials: false" in workflow
    preview = (ROOT / ".github/workflows/workbuddy-preview.yml").read_text(encoding="utf-8")
    assert "contents: write" not in preview and "pull_request_target" not in preview
    assert "WORKBUDDY_TEST_UVX" in preview


def test_upstream_body_comparison_uses_git_blob_on_crlf_checkout(tmp_path, monkeypatch):
    module = builder()
    skill = tmp_path / "qdrant-memory"
    skill.mkdir()
    canonical = b"---\nmetadata:\n  version: 0.2.5\n---\n# Canonical body\n"
    generated = b"---\nversion: 0.2.5\n---\n# Canonical body\n"
    (skill / "SKILL.md").write_bytes(canonical.replace(b"\n", b"\r\n"))
    monkeypatch.setattr(module, "validate_skill_source", lambda *a: None)
    monkeypatch.setattr(module, "git", lambda *a: canonical.decode().strip())
    # Keep source blob byte-exact, including the final newline.
    def source_blob(*args, **kwargs):
        return canonical
    monkeypatch.setattr(module.subprocess, "check_output", source_blob)
    def upstream_builder(command, **kwargs):
        output = Path(command[-1]) / "skill.zip"
        output.write_bytes(module.archive_bytes({"qdrant-memory/SKILL.md": (generated, 0o644), "qdrant-memory/LICENSE": (b"MIT", 0o644)}))
    monkeypatch.setattr(module.subprocess, "run", upstream_builder)
    files = module.skill_files(tmp_path, {"version": "0.2.5"})
    assert files["skills/qdrant-memory/SKILL.md"][0] == generated


def test_connector_bytes_ignore_checkout_line_ending_translation(tmp_path, monkeypatch):
    module = builder()
    monkeypatch.setattr(module, "skill_files", lambda *a: {"skills/qdrant-memory/SKILL.md": (b"generated\n", 0o644), "skills/qdrant-memory/LICENSE": (b"MIT\n", 0o644)})
    roots = [tmp_path / "lf", tmp_path / "crlf"]
    names = ["pyproject.toml", "runtime-source.json", "integrations/workbuddy/connector-meta.json", "integrations/workbuddy/mcp.json", "integrations/workbuddy/skill-source.json", "integrations/workbuddy/icon.svg"]
    for index, root in enumerate(roots):
        for name in names:
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
            destination.write_bytes(data if index == 0 else data.replace(b"\n", b"\r\n"))
    one = module.build(roots[0], tmp_path, tmp_path / "one")[0]
    two = module.build(roots[1], tmp_path, tmp_path / "two")[0]
    assert one.read_bytes() == two.read_bytes()
