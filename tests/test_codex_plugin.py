"""Portable package invariants and thin Node host-boundary behavior."""

import importlib.util
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "codex_package", ROOT / "scripts/build_codex_plugin.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def _launcher_for_installed_distribution(tmp_path):
    """Build an isolated test plugin pinned to the installed test distribution."""
    import shutil
    from importlib.metadata import version

    plugin = tmp_path / "plugin-under-test"
    plugin.mkdir()
    shutil.copy2(ROOT / "plugins/qdrant-memory/launcher.mjs", plugin / "launcher.mjs")
    release = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())
    release["mcp_distribution_version"] = version("qdrant-memory-mcp")
    (plugin / "release.json").write_text(json.dumps(release), encoding="utf-8")
    return plugin / "launcher.mjs"


def test_portable_package():
    """Keep plugin manifests, marketplace metadata, and dependency pins aligned."""
    assert package.validate()["version"] == "0.1.4"
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert marketplace["name"] == "cnkang"
    assert marketplace["interface"]["displayName"] == "Kang's plugins"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/qdrant-memory"
    release = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())
    assert release["plugin_version"] == "0.1.4"
    assert release["skill_version"] == "0.4.4"
    assert release["mcp_distribution_version"] == "0.3.3"
    assert len(release["runtime_commit"]) == len(release["skill_commit"]) == 40
    requirements = (ROOT / "plugins/qdrant-memory/requirements.txt").read_text()
    assert (
        f"hermes-plugin-qdrant-memory[mcp,local]=={release['runtime_version']}"
        in requirements
    )
    assert release["runtime_commit"] not in requirements
    assert "git+https://github.com/cnkang/hermes-plugin-qdrant-memory" not in requirements
    assert "qdrant-memory-mcp==" + release["mcp_distribution_version"] in requirements


def test_codex_openai_compatibility_overlay_is_the_active_fallback():
    """Keep OpenAI-specific settings in the overlay fallback, not root plugin.json."""
    portable = json.loads(
        (ROOT / "plugins/qdrant-memory/plugin.json").read_text(encoding="utf-8")
    )
    portable_mcp = json.loads(
        (ROOT / "plugins/qdrant-memory/mcp.json").read_text(encoding="utf-8")
    )
    overlay = json.loads(
        (ROOT / "plugins/qdrant-memory/.codex-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert portable["name"] == overlay["name"] == "qdrant-memory"
    assert portable["version"] == overlay["version"]
    assert portable.get("extensions", {}).get("com.openai") is None
    assert set(portable_mcp) == {"$schema", "mcpServers"}
    assert portable_mcp["$schema"] == (
        "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    )

    openai = overlay["extensions"]["com.openai"]
    assert openai["onboardingSkill"] == "./skills/setup/SKILL.md"
    assert openai["interface"]["displayName"] == "Qdrant Memory for Codex"
    assert openai["interface"]["defaultPrompt"]
    assert set(overlay["mcpServers"]) == set(portable_mcp["mcpServers"])

    expected_env_vars = [
        "QDRANT_MEMORY_CODEX_ROOT",
        "QDRANT_MEMORY_CODEX_PROFILE",
        "QDRANT_MEMORY_CODEX_EXECUTABLE",
        "QDRANT_MEMORY_CODEX_PYTHON",
        "QDRANT_MEMORY_CODEX_OWNER_URL",
        "QDRANT_MEMORY_SHARED_TOKEN",
        "QDRANT_API_KEY",
        "EMBEDDING_API_KEY",
    ]
    portable_server = portable_mcp["mcpServers"]["qdrant-memory"]
    codex_server = overlay["mcpServers"]["qdrant-memory"]
    assert {key: codex_server.get(key) for key in portable_server} == portable_server
    assert len(codex_server["env_vars"]) == len(expected_env_vars)
    assert set(codex_server["env_vars"]) == set(expected_env_vars)


def test_builder_rejects_root_openai_extension_that_overrides_overlay(tmp_path):
    """Keep OpenAI settings in the overlay so MCP env forwarding stays effective."""
    import shutil

    plugin = tmp_path / "plugin"
    shutil.copytree(package.PLUGIN, plugin)
    manifest_path = plugin / "plugin.json"
    overlay_path = plugin / ".codex-plugin/plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    manifest["extensions"] = {
        "com.openai": overlay["extensions"]["com.openai"]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="Root OpenAI extension is unsupported"):
        package.validate(plugin)


@pytest.mark.parametrize(
    "inline_extension",
    [{}, {"onboardingSkill": "./skills/setup/SKILL.md"}],
)
def test_builder_rejects_malformed_inline_extension_without_using_fallback(
    tmp_path, inline_extension
):
    """Reject any root OpenAI extension that would suppress the Codex overlay."""
    import shutil

    plugin = tmp_path / "plugin"
    shutil.copytree(package.PLUGIN, plugin)
    manifest_path = plugin / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extensions"] = {"com.openai": inline_extension}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="Root OpenAI extension is unsupported"):
        package.validate(plugin)


@pytest.mark.parametrize(
    "declared, expected",
    [
        ("exact", True),
        ("reordered", True),
        ("missing", False),
        ("extra", False),
        ("duplicate", False),
        ("wrong_location", False),
    ],
)
def test_codex_e2e_checks_json_config_allowlist_not_text_substrings(
    monkeypatch, tmp_path, declared, expected
):
    """Inspect only effective JSON field names and never retain env values."""
    from test_release_guards import load_script

    e2e = load_script("codex_plugin_e2e")
    env_vars = list(e2e.ENV_VAR_NAMES)
    transport = {"env": {"SENTINEL_SECRET": "secret-value"}}
    if declared == "exact":
        transport["env_vars"] = env_vars
    elif declared == "reordered":
        transport["env_vars"] = list(reversed(env_vars))
    elif declared == "missing":
        transport["env_vars"] = env_vars[:-1]
    elif declared == "extra":
        transport["env_vars"] = env_vars + ["UNEXPECTED_VARIABLE"]
    elif declared == "duplicate":
        transport["env_vars"] = env_vars + [env_vars[0]]
    else:
        transport["env"] = {name: "secret-value" for name in env_vars}

    commands = []

    def fake_codex(argv, env, workdir, *, ok=True):
        commands.append(argv)
        return json.dumps({"name": "qdrant-memory", "transport": transport})

    monkeypatch.setattr(e2e, "codex", fake_codex)
    result = e2e.assert_env_forwarding_visible({}, tmp_path)

    assert commands == [["mcp", "get", "qdrant-memory", "--json"]]
    assert result["all_present"] is expected
    assert "secret-value" not in json.dumps(result)
    assert "SENTINEL_SECRET" not in json.dumps(result)
    if declared == "wrong_location":
        assert result["visible"] == []
    else:
        assert result["visible"] == transport["env_vars"]


def test_cli_archive_output_stays_inside_dist(tmp_path, monkeypatch):
    output_root = tmp_path / "dist"
    output_root.mkdir()
    monkeypatch.setattr(package, "ROOT", tmp_path)

    output = output_root / "qdrant-memory.zip"
    assert package.resolve_archive_output(output) == output
    assert package.resolve_archive_output(Path("dist/qdrant-memory.zip")) == output
    with pytest.raises(ValueError, match="dist directory"):
        package.resolve_archive_output(tmp_path.parent / "outside.zip")


def test_cli_archive_output_rejects_symlinked_dist(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "dist").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(package, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        package.resolve_archive_output(tmp_path / "dist/archive.zip")


def test_cli_archive_output_rejects_symlinked_parent(tmp_path, monkeypatch):
    output_root = tmp_path / "dist"
    output_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output_root / "nested").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(package, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="dist directory"):
        package.resolve_archive_output(output_root / "nested/archive.zip")


def test_cli_archive_output_rejects_output_symlink(tmp_path, monkeypatch):
    output_root = tmp_path / "dist"
    output_root.mkdir()
    target = output_root / "target.zip"
    target.write_bytes(b"archive")
    output = output_root / "plugin.zip"
    output.symlink_to(target)
    monkeypatch.setattr(package, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="output cannot be a symlink"):
        package.resolve_archive_output(output)


def test_cli_archive_output_requires_regular_file(tmp_path, monkeypatch):
    output_root = tmp_path / "dist"
    output_root.mkdir()
    output = output_root / "directory.zip"
    output.mkdir()
    monkeypatch.setattr(package, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="regular file"):
        package.resolve_archive_output(output)


def test_cli_rejects_external_output_before_building(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "ROOT", tmp_path)
    skill_repo = tmp_path / "skills"
    skill_repo.mkdir()
    output = tmp_path.parent / f"{tmp_path.name}-outside.zip"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_codex_plugin.py",
            "--skill-repo",
            str(skill_repo),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as error:
        package.main()

    assert error.value.code == 2
    assert not output.exists()


def test_cli_builds_to_validated_output_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(package, "ROOT", tmp_path)
    output_root = tmp_path / "dist"
    output_root.mkdir()
    skill_repo = tmp_path / "skills"
    skill_repo.mkdir()
    built = {}

    def fake_build(output, source):
        built.update(output=output, source=source)
        return {"sha256": "fixture"}

    monkeypatch.setattr(package, "build", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_codex_plugin.py",
            "--skill-repo",
            str(skill_repo),
            "--output",
            "dist/plugin.zip",
        ],
    )
    package.main()

    assert built == {
        "output": output_root / "plugin.zip",
        "source": skill_repo,
    }
    assert json.loads(capsys.readouterr().out) == {"sha256": "fixture"}


def test_skill_frontmatter_version_matches_release():
    """The packaged Skill snapshot must carry the release's pinned version."""
    release = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())
    lines = (
        (ROOT / "plugins/qdrant-memory/skills/qdrant-memory/SKILL.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert lines[0] == "---"
    end = lines.index("---", 1)
    metadata = lines.index("metadata:", 1, end)
    version = next(
        line.split(":", 1)[1].strip().strip('"')
        for line in lines[metadata + 1 : end]
        if line.strip().startswith("version:")
    )
    assert version == release["skill_version"]


def test_packaged_text_sources_use_lf_line_endings():
    """Keep source ZIP bytes stable when Windows checkout enables autocrlf."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "plugins/qdrant-memory/** text eol=lf" in attributes
    assert "docs/codex-plugin-verification.md text eol=lf" in attributes
    files = package.source_files()
    text_suffixes = {".json", ".md", ".mjs", ".py", ".txt", ".svg"}
    for name, data in files.items():
        if Path(name).suffix in text_suffixes or name.endswith("/LICENSE"):
            assert b"\r\n" not in data, name
    verification = package._source_bytes(ROOT / package.VERIFICATION_PATH)
    assert b"\r\n" not in verification


def test_text_byte_normalization_handles_archive_eols_and_preserves_binary():
    assert (
        package._normalize_text_bytes(
            "references/setup.md", b"first\r\nsecond\rthird\n"
        )
        == b"first\nsecond\nthird\n"
    )
    binary = b"\x00\xff\r\n"
    assert package._normalize_text_bytes("model.bin", binary) == binary
    with pytest.raises(ValueError, match="not UTF-8"):
        package._normalize_text_bytes("README.md", b"\xff")


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


def test_builder_reads_checked_descriptor(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"approved")
    monkeypatch.setattr(
        Path, "read_bytes", lambda *_: pytest.fail("path read fallback")
    )
    assert package._source_bytes(source) == b"approved"


def test_builder_rejects_file_replacement_between_stat_and_open(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"approved")

    def replace():
        source.rename(tmp_path / "original")
        source.write_bytes(b"unapproved")

    if os.name == "nt":
        original = package._windows_source_handle

        def open_file(path, directory):
            if not directory:
                replace()
            return original(path, directory)

        monkeypatch.setattr(package, "_windows_source_handle", open_file)
    else:
        original = os.open

        def open_file(path, *args, **kwargs):
            if path == source.name:
                replace()
            return original(path, *args, **kwargs)

        monkeypatch.setattr(os, "open", open_file)
        monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {open_file})
    with pytest.raises(ValueError, match="changed during open"):
        package._source_bytes(source)


def test_builder_rejects_parent_substitution_after_precheck(tmp_path, monkeypatch):
    plugin = tmp_path / package.PLUGIN_PATH
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text("approved")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plugin.json").write_text("unapproved")
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "PLUGIN", plugin)
    monkeypatch.setattr(
        package, "git", lambda *_: (package.PLUGIN_PATH + "/plugin.json\0").encode()
    )
    original = package._source_bytes

    def substitute(path):
        plugin.rename(tmp_path / "original")
        if os.name == "nt":
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(plugin), str(outside)],
                check=True,
                capture_output=True,
            )
        else:
            plugin.symlink_to(outside, target_is_directory=True)
        return original(path)

    monkeypatch.setattr(package, "_source_bytes", substitute)
    with pytest.raises((OSError, ValueError)):
        package.source_files()


def test_builder_rejects_redirected_file_even_if_precheck_metadata_matches(
    tmp_path, monkeypatch
):
    source, outside = tmp_path / "source", tmp_path / "outside"
    source.write_bytes(b"approved")
    outside.write_bytes(b"unapproved")
    if os.name == "nt":
        redirected = outside.lstat()
        original_stat = Path.lstat
        original_open = package._windows_source_handle
        monkeypatch.setattr(
            Path,
            "lstat",
            lambda path: redirected if path == source else original_stat(path),
        )
        monkeypatch.setattr(
            package,
            "_windows_source_handle",
            lambda path, directory: original_open(
                path if directory else outside, directory
            ),
        )
    else:
        original_open = os.open

        def redirect(path, *args, **kwargs):
            return original_open(
                str(outside) if path == source.name else path, *args, **kwargs
            )

        monkeypatch.setattr(os, "open", redirect)
        monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {redirect})
    with pytest.raises(
        ValueError, match="outside its checked path|changed during open"
    ):
        package._source_bytes(source)


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
    """Verify the install smoke uses its selected Codex CLI and cleans up."""
    import sys
    from test_release_guards import load_script

    smoke = load_script("codex_install_smoke")
    home, cache = tmp_path / "home", tmp_path / "cache"
    (cache / "skills/setup").mkdir(parents=True)
    (cache / "skills/setup/SKILL.md").write_text("fixture")
    (cache / "plugin.json").write_text(json.dumps({"name": "qdrant-memory"}))
    (cache / ".codex-plugin").mkdir()
    (cache / ".codex-plugin/plugin.json").write_text(
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
                    "version": "invalid" if wrong_version else smoke.PLUGIN_VERSION,
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
    source_skill = plugin / "skills/qdrant-memory"
    shutil.rmtree(source_skill)
    source_skill.mkdir(parents=True)
    data = b"---\nname: qdrant-memory\n---\nupstream skill\n"
    (source_skill / "SKILL.md").write_bytes(data)
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
    (source_skill / "SKILL.md").write_bytes(data + b"mismatch\n")
    with pytest.raises(ValueError, match="does not match its pinned snapshot"):
        package.build(output, tmp_path)
    (source_skill / "SKILL.md").write_bytes(data)
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert {info.compress_type for info in archive.infolist()} == {
            zipfile.ZIP_STORED
        }
        assert {info.create_system for info in archive.infolist()} == {3}
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
    checked_read = package._source_bytes

    def refuse_evidence(path):
        if path == verification:
            raise ValueError("evidence must use the checked source reader")
        return checked_read(path)

    monkeypatch.setattr(package, "_source_bytes", refuse_evidence)
    with pytest.raises(ValueError, match="checked source reader"):
        package.build(output, tmp_path)


def test_skill_source_boundary_remains_narrow():
    import pytest
    from test_release_guards import load_script

    metadata = load_script("verify_metadata")
    metadata.check_source_layout(["plugins/qdrant-memory/skills/setup/SKILL.md"])
    for forbidden in ("SKILL.md", "qdrant_memory/SKILL.md", "plugins/other/SKILL.md"):
        with pytest.raises(AssertionError):
            metadata.check_source_layout([forbidden])


@pytest.mark.parametrize("filename", ["plugin.json", "mcp.json"])
def test_archive_validates_the_collected_manifest_bytes(
    tmp_path, monkeypatch, filename
):
    import shutil

    plugin = tmp_path / package.PLUGIN_PATH
    shutil.copytree(package.PLUGIN, plugin)
    skill_root = plugin / "skills/qdrant-memory"
    shutil.rmtree(skill_root)
    skill_root.mkdir(parents=True)
    skill_bytes = b"---\nname: qdrant-memory\n---\nfixture\n"
    (skill_root / "SKILL.md").write_bytes(skill_bytes)
    (tmp_path / "docs").mkdir()
    (tmp_path / package.VERIFICATION_PATH).write_text("fixture evidence")
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
    package.validate(plugin)
    target = plugin / filename
    original = package._source_bytes
    changed = []

    def edit_in_place(path):
        if path == target:
            document = json.loads(path.read_text(encoding="utf-8"))
            if filename == "plugin.json":
                document["name"] = "invalid-name"
            else:
                document["mcpServers"]["qdrant-memory"]["command"] = "unapproved"
            path.write_text(json.dumps(document), encoding="utf-8")
            changed.append(path)
        return original(path)

    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "PLUGIN", plugin)
    monkeypatch.setattr(package, "_source_bytes", edit_in_place)
    monkeypatch.setattr(
        package,
        "skill_files",
        lambda *_: {
            "skills/qdrant-memory/SKILL.md": skill_bytes,
        },
    )
    with pytest.raises(
        ValueError,
        match="Invalid plugin name|Compatibility MCP mismatch|Invalid MCP command",
    ):
        package.build(tmp_path / "plugin.zip", tmp_path)
    assert changed == [target]
    assert not (tmp_path / "plugin.zip").exists()


def test_node_paths_do_not_reuse_hermes():
    """Keep Codex plugin paths independent from Hermes defaults."""
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
  assert.equal(paths.python, join(home, '.qdrant-memory', 'codex', 'runtime',
    platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'python.exe' : 'python'));
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


def test_launcher_rejects_stale_mcp_pin():
    """Refuse plugin startup when the reusable environment has an old MCP pin."""
    script = """
import { assertMcpVersion } from './plugins/qdrant-memory/launcher.mjs';
import assert from 'node:assert/strict';
const release = {mcp_distribution_version: '0.3.3'};
assert.doesNotThrow(() => assertMcpVersion(release, '0.3.3'));
assert.throws(() => assertMcpVersion(release, '0.3.2'), /setup skill/);
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


def test_launcher_fails_when_runtime_venv_lacks_mcp_distribution(tmp_path):
    """A runtime venv without the pinned MCP package fails closed before startup."""
    import os
    import sys

    stub = tmp_path / "runtime-bin"
    stub.mkdir()
    executable = stub / (
        "qdrant-memory.exe"
        if __import__("sys").platform == "win32"
        else "qdrant-memory"
    )
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    env = {
        **os.environ,
        "QDRANT_MEMORY_CODEX_EXECUTABLE": str(executable),
        "QDRANT_MEMORY_CODEX_PYTHON": sys.executable,
        "QDRANT_MEMORY_CODEX_PROFILE": str(tmp_path / "profile"),
    }
    result = subprocess.run(
        ["node", str(ROOT / "plugins/qdrant-memory/launcher.mjs"), "mcp"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "No data was reset" in result.stderr
    assert not (tmp_path / "profile").exists()


def test_node_entrypoint_real_mcp(sandbox):
    """Run the portable plugin bridge against an installed MCP runtime."""
    import asyncio
    import shutil
    import sys
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
        QDRANT_MEMORY_CODEX_PYTHON=sys.executable,
    )
    launcher = _launcher_for_installed_distribution(profile.parent)
    shadow_cwd = profile.parent / "shadow-cwd"
    source_metadata = shadow_cwd / "qdrant_memory_mcp.egg-info"
    source_metadata.mkdir(parents=True)
    (source_metadata / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: qdrant-memory-mcp\nVersion: 999.0.0\n",
        encoding="utf-8",
    )
    mismatch = profile.parent / "mismatched-runtime" / runtime.name
    mismatch.parent.mkdir()
    shutil.copy2(runtime, mismatch)
    mismatch_env = {
        **env,
        "QDRANT_MEMORY_CODEX_EXECUTABLE": str(mismatch),
    }
    rejected = subprocess.run(
        ["node", str(launcher), "mcp"],
        env=mismatch_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert rejected.returncode == 1
    assert "No data was reset" in rejected.stderr

    async def scenario():
        params = StdioServerParameters(
            command="node",
            args=[str(launcher), "mcp"],
            env=env,
            cwd=str(shadow_cwd),
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


def test_node_entrypoint_scope_isolation(sandbox):
    """A sibling profile must not observe another profile's stored records."""
    import asyncio
    import json
    import sys
    import sysconfig
    import subprocess

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    profile, _, config, env, _, _, _ = sandbox
    runtime = Path(sysconfig.get_path("scripts")) / (
        "qdrant-memory.exe"
        if __import__("sys").platform == "win32"
        else "qdrant-memory"
    )
    sibling = profile.parent / "sibling-profile"
    sibling.mkdir()
    scoped = {**config, "scope": {"user_id": "other-user", "agent_id": "other-agent"}}
    (sibling / "qdrant-memory.json").write_text(json.dumps(scoped), encoding="utf-8")
    init = subprocess.run(
        [str(runtime), "--home", str(sibling), "init"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not json.loads(init.stdout).get("error"), init.stdout
    launcher = _launcher_for_installed_distribution(profile.parent)
    shadow_cwd = profile.parent / "shadow-cwd"
    source_metadata = shadow_cwd / "qdrant_memory_mcp.egg-info"
    source_metadata.mkdir(parents=True)
    (source_metadata / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: qdrant-memory-mcp\nVersion: 999.0.0\n",
        encoding="utf-8",
    )

    def launcher_session(target):
        params = StdioServerParameters(
            command="node",
            args=[str(launcher), "mcp"],
            env={
                **env,
                "QDRANT_MEMORY_CODEX_PROFILE": str(target),
                "QDRANT_MEMORY_CODEX_EXECUTABLE": str(runtime),
                "QDRANT_MEMORY_CODEX_PYTHON": sys.executable,
            },
            cwd=str(shadow_cwd),
        )

        @asynccontextmanager
        async def session():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as live:
                    await live.initialize()
                    yield live

        return session

    async def scenario():
        control = "scope-isolation-control-fixture"
        async with launcher_session(profile)() as first:
            added = await first.call_tool("qdrant_memory_add", {"text": control})
            payload = json.loads(added.content[0].text)
            assert not added.model_dump(by_alias=True)["isError"]
            record_id = payload["id"] if "id" in payload else None

        async with launcher_session(sibling)() as second:
            leak = await second.call_tool(
                "qdrant_memory_search", {"query": "scope-isolation-control-fixture"}
            )
            search_blob = leak.model_dump(by_alias=True)
            assert not search_blob["isError"]
            memories = json.loads(search_blob["content"][0]["text"])["memories"]
            assert memories == []
            # An exact-ID delete against another profile's record must fail, not
            # silently succeed.
            if record_id:
                denial = await second.call_tool(
                    "qdrant_memory_delete", {"id": record_id}
                )
                assert denial.model_dump(by_alias=True)["isError"]

        async with launcher_session(profile)() as third:
            kept = await third.call_tool(
                "qdrant_memory_search", {"query": "scope-isolation-control-fixture"}
            )
            memories = json.loads(kept.content[0].text)["memories"]
            assert any(row["text"] == control for row in memories)

    asyncio.run(scenario())
