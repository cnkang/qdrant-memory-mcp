"""Keep public release acceptance and documented launchers on the selected version."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_readmes_prioritize_stable_stdio_and_label_host_candidates():
    """Keep stable installation first and host artifact claims separate."""
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    for name, text, quickstart in (
        ("README.md", english, "docs/quickstart.md"),
        ("README.zh-CN.md", chinese, "docs/quickstart.zh-CN.md"),
    ):
        assert quickstart in text[:2500], name
        assert "qdrant-memory-mcp==0.3.5" in text
        assert "Runtime 0.7.1" in text
        assert "0.2.0-rc.3" in text
        assert "0.1.0-rc.12" in text
        assert "0.1.0-rc.10" in text
        assert "Runtime 0.6.2" in text
        assert (
            "public directory" in text.lower()
            or "public plugin directory" in text.lower()
            or "公共插件目录" in text
        ), name
        assert "npm package is private" not in text
        assert "npm 包仍为 private" not in text
        assert "GUI Marketplace" in text or "Marketplace GUI" in text

    for name in ("docs/quickstart.md", "docs/quickstart.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "qdrant-memory-mcp==0.3.5" in text
        assert "Runtime 0.7.1" in text
        assert "--force" in text
        assert "does not automatically" in text or "不会自动提取" in text
        assert "recreate the profile" in text or "重建 profile" in text


def test_public_protocol_install_tracks_project_version(tmp_path):
    """Execute the workflow's version lookup against a future synthetic release."""
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    step = workflow.split(
        "- name: Verify publicly installed package and uvx protocol", 1
    )[1]
    step = step.split("- uses:", 1)[0]
    assignment = re.search(r"(\w+)=\$\((python -c .+)\)", step)
    assert assignment, (
        "Public verification must derive its version from project metadata"
    )
    variable, command = assignment.groups()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "9.8.7"\n', encoding="utf-8"
    )
    argv = shlex.split(command)
    result = subprocess.run(
        [sys.executable, *argv[1:]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == "9.8.7"
    install = next(line for line in step.splitlines() if "-m pip install" in line)
    arguments = shlex.split(install)
    expanded = [
        value.replace(f"${variable}", result.stdout.strip()) for value in arguments
    ]
    assert "qdrant-memory-mcp==9.8.7" in expanded
    assert not any("find-links" in value for value in arguments)


def test_current_workbuddy_and_dsh_instructions_track_project_version():
    """Keep current integration instructions aligned with public MCP pins."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = f"qdrant-memory-mcp=={project['project']['version']}"
    published_requirement = "qdrant-memory-mcp==0.3.5"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    candidate_docs = [
        "docs/quickstart.zh-CN.md",
        "docs/quickstart.md",
        "docs/dsh-integration.md",
        "docs/dsh-integration.zh-CN.md",
        "integrations/workbuddy/README.md",
    ]
    assert requirement in readme
    for relative in candidate_docs:
        contents = (ROOT / relative).read_text(encoding="utf-8")
        assert requirement in contents, relative
        if relative.startswith(("docs/dsh-integration", "integrations/workbuddy/README")):
            assert published_requirement in contents, relative
        if relative.startswith("docs/dsh-integration"):
            assert (
                f"qdrant-memory-mcp-{published_requirement.rsplit('==', 1)[1]}.cordis.yml"
                in contents
            ), relative
            assert (
                "raw.githubusercontent.com/cnkang/qdrant-memory-mcp/main/"
                "integrations/dsh/qdrant-memory.cordis.yml"
            ) in contents, relative

    # The DSH source overlay and WorkBuddy uvx alternative use the public
    # package version that the setup instructions document.
    overlay = (ROOT / "integrations/dsh/qdrant-memory.cordis.yml").read_text(
        encoding="utf-8"
    )
    active_pins = re.findall(
        r"(?m)^\s+- (qdrant-memory-mcp==\S+)\s*$", overlay
    )
    assert active_pins == [requirement]
    assert requirement in (ROOT / "integrations/workbuddy/mcp.uvx.json").read_text(
        encoding="utf-8"
    )

    runtime_version = project["project"]["dependencies"][0].rsplit("==", 1)[1]
    architecture = (ROOT / "docs/cross-harness-architecture.md").read_text(
        encoding="utf-8"
    )
    assert f"| Python MCP | {project['project']['version']} |" in architecture
    assert f"| Runtime | {runtime_version} |" in architecture


def test_dsh_documented_install_commands_match_pinned_bundle():
    """Keep each documented DSH install command tied to the prepared launcher."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    launcher = json.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))
    bundle = json.loads(
        (ROOT / "integrations/dsh/bundle/package.json").read_text(encoding="utf-8")
    )
    runtime_version = project["project"]["dependencies"][0].rsplit("==", 1)[1]
    assert launcher["runtime_version"] == runtime_version
    assert f"@cnkang/qdrant-memory-launcher@{launcher['version']}" in (
        ROOT / "integrations/dsh/bundle/index.js"
    ).read_text(encoding="utf-8")
    for relative in (
        "docs/dsh-integration.md",
        "docs/dsh-integration.zh-CN.md",
        "integrations/dsh/bundle/README.md",
    ):
        contents = (ROOT / relative).read_text(encoding="utf-8")
        assert (
            f"@cnkang/qdrant-memory-launcher@{launcher['version']} prepare dsh"
            in contents
        ), relative
        assert (
            "dsh plugin --profile <name> add "
            f"@cnkang/qdrant-memory-dsh-bundle@{bundle['version']}"
            in contents
        ), relative
        assert (
            "dsh plugin --profile <name> add "
            "@cnkang/qdrant-memory-dsh-bundle\n"
        ) not in contents, relative


def test_workbuddy_readme_separates_published_and_next_launcher():
    """The published Connector 0.2.6 pin must not drift with the next build."""
    guide = (ROOT / "integrations/workbuddy/README.md").read_text(encoding="utf-8")
    mcp = json.loads(
        (ROOT / "integrations/workbuddy/mcp.json").read_text(encoding="utf-8")
    )
    args = mcp["mcpServers"]["qdrant-memory"]["args"]
    assert "0.1.0-rc.11" not in guide
    assert "0.1.0-rc.10" in guide
    assert "selects launcher 0.1.0-rc.12, Runtime 0.7.1 and Skill 0.4.6" in guide
    assert any("0.1.0-rc.12" in value for value in args)


def test_dsh_tarball_fallback_uses_the_npm_registry():
    """A missing mirror must not point users at a nonexistent GitHub asset."""
    bundle = json.loads(
        (ROOT / "integrations/dsh/bundle/package.json").read_text(encoding="utf-8")
    )
    version = bundle["version"]
    tarball = (
        "https://registry.npmjs.org/@cnkang/qdrant-memory-dsh-bundle/-/"
        f"qdrant-memory-dsh-bundle-{version}.tgz"
    )
    for relative in (
        "docs/dsh-integration.md",
        "docs/dsh-integration.zh-CN.md",
        "integrations/dsh/bundle/README.md",
    ):
        contents = (ROOT / relative).read_text(encoding="utf-8")
        assert tarball in contents, relative
        assert "dist.tarball dist.integrity" in contents, relative
        assert "repository release" not in contents.lower(), relative
        assert "仓库 Release" not in contents, relative
        assert (
            f"dsh plugin --profile <name> add "
            f"./qdrant-memory-dsh-bundle-{version}.tgz"
        ) in contents, relative


def test_workbuddy_migration_confirms_empty_exports_on_shell_and_powershell():
    """Require operators to confirm an empty WorkBuddy migration export."""
    guide = (ROOT / "integrations/workbuddy/README.md").read_text(encoding="utf-8")

    assert guide.count("Export count does not match exported memories.") == 2
    assert 'if [ "$EXPORT_COUNT" -eq 0 ]; then' in guide
    assert 'if [ "$CONFIRM_EMPTY_EXPORT" != yes ]; then' in guide
    assert "if ($ExportCount -eq 0) {" in guide
    assert "if ($ConfirmEmptyExport -cne 'yes')" in guide


def test_workbuddy_windows_rollback_stops_on_move_failures():
    """Ensure rollback catches non-terminating PowerShell move failures."""
    guide = (ROOT / "integrations/workbuddy/README.md").read_text(encoding="utf-8")
    rollback = guide.split("On Windows, disconnect WorkBuddy", 1)[1]
    block = rollback.split("```powershell\n", 1)[1].split("\n```", 1)[0]

    assert block.startswith("$ErrorActionPreference = 'Stop'\n")


def test_workbuddy_powershell_migration_example_parses_when_available(tmp_path):
    """Parse all documented PowerShell examples when PowerShell exists."""
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is unavailable on this platform.")

    guide = (ROOT / "integrations/workbuddy/README.md").read_text(encoding="utf-8")
    parser = (
        "$tokens = $null; $errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:WORKBUDDY_MIGRATION_SCRIPT, [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }"
    )
    blocks = re.findall(r"```powershell\n(.*?)\n```", guide, re.DOTALL)
    assert blocks
    for index, block in enumerate(blocks):
        script_path = tmp_path / f"workbuddy-example-{index}.ps1"
        script_path.write_text(block, encoding="utf-8")
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", parser],
            capture_output=True,
            text=True,
            env={**os.environ, "WORKBUDDY_MIGRATION_SCRIPT": str(script_path)},
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, f"PowerShell example {index}: {result.stderr}"
