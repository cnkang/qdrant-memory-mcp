"""Validate the fixed-version launch path and host configuration examples."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quickstarts_use_supported_fixed_version_uvx_syntax():
    """Keep setup commands in the quickstarts and host args in the READMEs."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    requirement = f"qdrant-memory-mcp=={version}"
    for name in ("docs/quickstart.md", "docs/quickstart.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        commands = re.findall(
            r"(?m)^uvx --from \S+ qdrant-memory-mcp --home .+ (init|doctor)$", text
        )
        assert set(commands) == {"init", "doctor"}, name
        assert f"uvx --from {requirement} qdrant-memory-mcp" in text

    for name in ("README.md", "README.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f'"--from", "{requirement}", "qdrant-memory-mcp"' in text, name
        assert "docs/quickstart" in text
