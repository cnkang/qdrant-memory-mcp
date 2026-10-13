"""Validate the published bilingual Registry command examples."""

import re
import shlex
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_registry_readme_commands_use_supported_uvx_syntax():
    """Check each launcher separates the package requirement from the command."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    requirement = f"qdrant-memory-mcp=={version}"
    for name in ("README.md", "README.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        commands = re.findall(r"`(uvx[^`\n]+)`", text)
        assert commands, f"{name} must document the default Registry launcher"
        for command in commands:
            argv = shlex.split(command)
            assert argv[:4] == ["uvx", "--from", requirement, "qdrant-memory-mcp"]
            assert argv[-1] == "mcp"
