"""Report whether this candidate can be tested through its exact public uvx pin."""

import importlib.util
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workbuddy_pypi_query", ROOT / "scripts/pypi_release.py")
query = importlib.util.module_from_spec(spec)
spec.loader.exec_module(query)
release = query.release


def available(root):
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    data = release(project, False)
    if data is None:
        return False
    info = data["info"]
    if info.get("name") != project["name"] or info.get("version") != project["version"] or info.get("requires_dist") != project["dependencies"] or "<!-- mcp-name: io.github.cnkang/qdrant-memory -->" not in info.get("description", ""):
        raise ValueError("Conflicting public MCP version, ownership or Runtime dependency")
    return True


def main():
    exists = available(ROOT)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"exists={str(exists).lower()}\n")
    print("Exact public uvx acceptance required" if exists else "Public uvx acceptance: NOT VERIFIED (candidate not yet published; protected publish workflow must verify after PyPI approval)")


if __name__ == "__main__":
    main()
