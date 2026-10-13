"""Check packaging, ownership, schema and source-free wheel before installation."""

import configparser
import json
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def verify():
    """Validate release metadata, launch configuration and source-free artifacts."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "schemas/server.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft7Validator(schema).validate(server)
    package = server["packages"][0]
    assert server["version"] == package["version"] == project["version"]
    assert package["identifier"] == project["name"] == "qdrant-memory-mcp"
    source = json.loads((ROOT / "runtime-source.json").read_text(encoding="utf-8"))
    assert project["dependencies"] == [
        f"hermes-plugin-qdrant-memory[mcp]=={source['version']}"
    ]
    assert len(source["commit"]) == 40 and all(
        c in "0123456789abcdef" for c in source["commit"]
    )
    for name in ("README.md", "README.zh-CN.md"):
        active = (ROOT / name).read_text(encoding="utf-8")
        assert f"qdrant-memory-mcp=={project['version']}" in active
        assert "qdrant-memory-mcp==0.1.0" not in active
    assert package["runtimeHint"] == "uvx" and package["transport"] == {"type": "stdio"}
    assert package["packageArguments"][-1] == {"type": "positional", "value": "mcp"}
    assert project["scripts"] == {"qdrant-memory-mcp": "qdrant_memory.standalone:main"}
    marker = f"<!-- mcp-name: {server['name']} -->"
    assert marker in (ROOT / "README.md").read_text(encoding="utf-8")
    assert not (ROOT / "qdrant_memory").exists() and not list(ROOT.rglob("SKILL.md"))
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        assert all(".dist-info/" in name for name in names), (
            "Wheel must contain metadata only"
        )
        metadata = BytesParser().parsebytes(
            wheel.read(next(n for n in names if n.endswith("/METADATA")))
        )
        assert metadata["Version"] == project["version"]
        assert metadata.get_all("Requires-Dist") == project["dependencies"]
        assert marker in metadata.get_payload()
        entry = configparser.ConfigParser()
        entry.read_string(
            wheel.read(
                next(n for n in names if n.endswith("entry_points.txt"))
            ).decode()
        )
        assert dict(entry["console_scripts"]) == project["scripts"]
    with tarfile.open(sdists[0]) as archive:
        assert not any("/docs/superpowers/" in n for n in archive.getnames())
        assert not any(
            "/qdrant_memory/" in n or n.endswith("/SKILL.md")
            for n in archive.getnames()
        )
    print(
        "Metadata, pinned dependency, ownership marker, schema and metadata-only artifacts verified"
    )


if __name__ == "__main__":
    verify()
