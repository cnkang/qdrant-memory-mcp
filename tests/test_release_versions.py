"""Keep public release acceptance and documented launchers on the selected version."""

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
    """Ensure published integration instructions use the current release."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = f"qdrant-memory-mcp=={project['project']['version']}"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    paths = [
        "docs/quickstart.zh-CN.md",
        "docs/quickstart.md",
        "docs/dsh-integration.md",
        "docs/dsh-integration.zh-CN.md",
        "integrations/dsh/qdrant-memory.cordis.yml",
        "integrations/workbuddy/README.md",
        "integrations/workbuddy/mcp.uvx.json",
    ]
    assert requirement in readme
    for relative in paths:
        assert requirement in (ROOT / relative).read_text(encoding="utf-8"), relative

    runtime_version = project["project"]["dependencies"][0].rsplit("==", 1)[1]
    architecture = (ROOT / "docs/cross-harness-architecture.md").read_text(encoding="utf-8")
    assert f"| Python MCP | {project['project']['version']} |" in architecture
    assert f"| Runtime | {runtime_version} |" in architecture


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
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, f"PowerShell example {index}: {result.stderr}"
