"""Keep public release acceptance and documented launchers on the selected version."""

import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

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
