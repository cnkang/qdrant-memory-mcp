"""Portable package invariants and thin Node host-boundary behavior."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "codex_package", ROOT / "scripts/build_codex_plugin.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_portable_package():
    assert package.validate()["version"] == "0.1.1"
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert marketplace["name"] == "cnkang"
    assert marketplace["interface"]["displayName"] == "Kang's plugins"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/qdrant-memory"
    release = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())
    assert len(release["runtime_commit"]) == len(release["skill_commit"]) == 40
    requirements = (ROOT / "plugins/qdrant-memory/requirements.txt").read_text()
    assert release["runtime_commit"] in requirements
    assert "qdrant-memory-mcp==" + release["mcp_distribution_version"] in requirements


def test_validation_survives_python_optimization(tmp_path):
    import shutil
    import sys

    plugin = tmp_path / "plugin"
    shutil.copytree(package.PLUGIN, plugin)
    manifest = json.loads((plugin / "plugin.json").read_text())
    manifest["name"] = "invalid-name"
    (plugin / "plugin.json").write_text(json.dumps(manifest))
    script = (
        "import runpy,sys; "
        "from pathlib import Path; "
        "runpy.run_path(sys.argv[1])['validate'](Path(sys.argv[2]))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            script,
            str(ROOT / "scripts/build_codex_plugin.py"),
            str(plugin),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Invalid plugin name" in result.stderr


def test_builder_rejects_git_option_injection(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="Unsupported"):
        package.git(tmp_path, "archive", "--output=unapproved", "qdrant-memory")
    with pytest.raises(ValueError, match="Unsupported"):
        package.git(tmp_path, "config", "alias.bad", "!unapproved")


def test_builder_rejects_symlinked_source_parent(tmp_path, monkeypatch):
    import pytest

    plugin = tmp_path / package.PLUGIN_PATH
    source = plugin / "skills/setup"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("approved tracked content")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    outside = tmp_path / "unapproved"
    source.rename(outside)
    (outside / "SKILL.md").write_text("unapproved replacement")
    try:
        source.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows account cannot create symlinks")
        raise
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "PLUGIN", plugin)
    with pytest.raises(ValueError, match="symlinks"):
        package.source_files()


def test_builder_rejects_missing_tracked_source(tmp_path, monkeypatch):
    """A tracked plugin file absent from the tree cannot be silently dropped."""
    plugin = tmp_path / package.PLUGIN_PATH
    plugin.mkdir(parents=True)
    tracked = plugin / "plugin.json"
    tracked.write_text("{}")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True
    )
    tracked.unlink()
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "PLUGIN", plugin)
    with pytest.raises(ValueError, match="missing"):
        package.source_files()


def test_pinned_skill_archive_requires_entrypoint(monkeypatch):
    import io
    import tarfile
    import pytest

    snapshot = io.BytesIO()
    with tarfile.open(fileobj=snapshot, mode="w") as archive:
        data = b"reference without entrypoint"
        member = tarfile.TarInfo("qdrant-memory/references/usage.md")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    monkeypatch.setattr(package, "git", lambda *args: snapshot.getvalue())
    with pytest.raises(ValueError, match="lacks SKILL.md"):
        package.skill_files(ROOT, "0" * 40)


@pytest.mark.parametrize("wrong_version", [False, True])
def test_install_smoke_uses_resolved_cli_and_checks_lifecycle(
    tmp_path, monkeypatch, capsys, wrong_version
):
    import sys
    from test_release_guards import load_script

    smoke = load_script("codex_install_smoke")
    home, cache = tmp_path / "home", tmp_path / "cache"
    (cache / "skills/setup").mkdir(parents=True)
    (cache / "skills/setup/SKILL.md").write_text("fixture")
    (cache / "plugin.json").write_text(
        json.dumps(
            {
                "extensions": {
                    "com.openai": {"onboardingSkill": "./skills/setup/SKILL.md"}
                }
            }
        )
    )
    resolved = str(tmp_path / "npm-bin/codex.cmd")
    calls = []

    def cli(argv, *, env, **_):
        assert argv[0] == resolved
        assert env["CODEX_HOME"] == str(home)
        calls.append(argv[1:])
        if argv[1:3] == ["plugin", "add"]:
            (home / "config.toml").write_text("enabled = true\n")
            return json.dumps(
                {
                    "version": "invalid" if wrong_version else "0.1.1",
                    "installedPath": str(cache),
                }
            )
        if argv[1:3] == ["plugin", "list"]:
            assert (home / "config.toml").read_text() == "enabled = false\n"
            return json.dumps(
                {"installed": [{"pluginId": smoke.PLUGIN_ID, "enabled": False}]}
            )
        if argv[1:3] == ["plugin", "remove"]:
            import shutil

            shutil.rmtree(cache)
        return "codex fixture" if argv[1:] == ["--version"] else "{}"

    monkeypatch.setattr(smoke.shutil, "which", lambda *a, **kw: resolved)
    monkeypatch.setattr(smoke.subprocess, "check_output", cli)
    monkeypatch.setattr(sys, "argv", ["smoke", "--home", str(home)])
    if wrong_version:
        with pytest.raises(RuntimeError, match="version mismatch"):
            smoke.main()
        assert capsys.readouterr().out == ""
        return
    smoke.main()
    report = json.loads(capsys.readouterr().out)
    assert report["setup_file_present"]
    assert "setup_discovered" not in report
    assert report["status"] == "PASS"
    assert ["plugin", "remove", smoke.PLUGIN_ID] in calls


def test_archive_uses_index_and_tracks_verification_edits(tmp_path, monkeypatch):
    import io
    import shutil
    import tarfile
    import zipfile

    plugin = tmp_path / "plugins/qdrant-memory"
    shutil.copytree(package.PLUGIN, plugin)
    docs = tmp_path / "docs"
    docs.mkdir()
    verification = docs / "codex-plugin-verification.md"
    verification.write_text("committed evidence")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    snapshot = io.BytesIO()
    with tarfile.open(fileobj=snapshot, mode="w") as archive:
        data = b"upstream skill"
        member = tarfile.TarInfo("qdrant-memory/SKILL.md")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    real_git = package.git
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "PLUGIN", plugin)
    archived = []

    def fake_git(repo, *args):
        if args[0] == "archive":
            archived.append(args[1])
            return snapshot.getvalue()
        return real_git(repo, *args)

    monkeypatch.setattr(package, "git", fake_git)
    output = tmp_path / "plugin.zip"
    assert not package.build(output, tmp_path)["source_dirty"]
    expected = json.loads((plugin / "release.json").read_text())["skill_commit"]
    assert archived == [expected]
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert {info.date_time for info in archive.infolist()} == {
            (2026, 1, 1, 0, 0, 0)
        }
    first = output.read_bytes()
    package.build(output, tmp_path)
    assert output.read_bytes() == first
    verification.write_text("edited evidence")
    assert package.build(output, tmp_path)["source_dirty"]
    (plugin / ".env").write_text("synthetic-untracked-private-file")
    (plugin / ".gitignore").write_text("ignored-private\n")
    (plugin / "ignored-private").write_text("synthetic-ignored-private-file")
    assert package.build(output, tmp_path)["source_dirty"]
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert not any(
            name.endswith(("/.env", "/ignored-private", "/.gitignore"))
            for name in names
        )
        assert archive.read("qdrant-memory/VERIFICATION.md") == b"edited evidence"
        assert json.loads(archive.read("qdrant-memory/release.json"))["source_dirty"]


def test_skill_source_boundary_remains_narrow():
    import pytest
    from test_release_guards import load_script

    metadata = load_script("verify_metadata")
    metadata.check_source_layout(["plugins/qdrant-memory/skills/setup/SKILL.md"])
    for forbidden in ("SKILL.md", "qdrant_memory/SKILL.md", "plugins/other/SKILL.md"):
        with pytest.raises(AssertionError):
            metadata.check_source_layout([forbidden])


def test_node_paths_do_not_reuse_hermes():
    script = """
import { locations } from './plugins/qdrant-memory/launcher.mjs';
import assert from 'node:assert/strict';
import { join, resolve } from 'node:path';
const home = resolve('synthetic-user');
for (const platform of ['linux', 'win32']) {
  const paths = locations({}, home, platform);
  assert.equal(paths.profile, join(home, '.qdrant-memory', 'codex', 'profile'));
  assert.equal(paths.executable, join(home, '.qdrant-memory', 'codex', 'runtime',
    platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'qdrant-memory.exe' : 'qdrant-memory'));
}
assert.throws(() => locations({QDRANT_MEMORY_CODEX_ROOT: 'relative'}, home), /Absolute paths/);
console.log('PASS');
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "PASS"


def test_missing_runtime_fails_without_writes(tmp_path):
    import os

    env = {**os.environ, "QDRANT_MEMORY_CODEX_ROOT": str(tmp_path / "absent")}
    result = subprocess.run(
        ["node", str(ROOT / "plugins/qdrant-memory/launcher.mjs"), "mcp"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "No data was reset" in result.stderr
    assert not (tmp_path / "absent").exists()


def test_node_entrypoint_real_mcp(sandbox):
    import asyncio
    import sysconfig

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    profile, _, _, env, _, _, _ = sandbox
    runtime = Path(sysconfig.get_path("scripts")) / (
        "qdrant-memory.exe"
        if __import__("sys").platform == "win32"
        else "qdrant-memory"
    )
    env.update(
        QDRANT_MEMORY_CODEX_PROFILE=str(profile),
        QDRANT_MEMORY_CODEX_EXECUTABLE=str(runtime),
    )

    async def scenario():
        params = StdioServerParameters(
            command="node",
            args=[str(ROOT / "plugins/qdrant-memory/launcher.mjs"), "mcp"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert {tool.name for tool in (await session.list_tools()).tools} == {
                    "qdrant_memory_search",
                    "qdrant_memory_add",
                    "qdrant_memory_update",
                    "qdrant_memory_delete",
                }
                result = await session.call_tool(
                    "qdrant_memory_add", {"text": "synthetic-codex-fixture"}
                )
                assert not result.model_dump(by_alias=True)["isError"]
                search = await session.call_tool(
                    "qdrant_memory_search", {"query": "synthetic-codex-fixture"}
                )
                assert not search.model_dump(by_alias=True)["isError"]
                records = json.loads(search.content[0].text)["memories"]
                assert any(row["text"] == "synthetic-codex-fixture" for row in records)

    asyncio.run(scenario())
