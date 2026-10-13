"""Assert the installable distribution remains a metadata-only upstream adapter."""

import configparser
import importlib.metadata
import json
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_metadata_contract():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    server = json.loads((ROOT / "server.json").read_text())
    assert project["dependencies"] == ["hermes-plugin-qdrant-memory[mcp]==0.2.0"]
    assert project["scripts"] == {"qdrant-memory-mcp": "qdrant_memory.standalone:main"}
    assert project["version"] == server["version"] == server["packages"][0]["version"]
    assert server["packages"][0]["identifier"] == project["name"]
    marker = f'<!-- mcp-name: {server["name"]} -->'
    assert marker in (ROOT / "README.md").read_text()
    assert not (ROOT / "qdrant_memory").exists()
    assert not list(ROOT.rglob("SKILL.md"))


def test_artifacts_are_metadata_only():
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        assert all(".dist-info/" in name for name in names)
        metadata = BytesParser().parsebytes(wheel.read(next(n for n in names if n.endswith("/METADATA"))))
        assert "<!-- mcp-name: io.github.cnkang/qdrant-memory -->" in metadata.get_payload()
        assert metadata.get_all("Requires-Dist") == ["hermes-plugin-qdrant-memory[mcp]==0.2.0"]
        entry = configparser.ConfigParser()
        entry.read_string(wheel.read(next(n for n in names if n.endswith("entry_points.txt"))).decode())
        assert entry["console_scripts"]["qdrant-memory-mcp"] == "qdrant_memory.standalone:main"
    with tarfile.open(sdists[0]) as archive:
        assert not any("/qdrant_memory/" in n or n.endswith("/SKILL.md") for n in archive.getnames())


def test_installed_entrypoint():
    dist = importlib.metadata.distribution("qdrant-memory-mcp")
    assert dist.version == "0.1.0"
    runtime = importlib.metadata.distribution("hermes-plugin-qdrant-memory")
    assert runtime.version == "0.2.0"
    assert importlib.metadata.packages_distributions()["qdrant_memory"] == ["hermes-plugin-qdrant-memory"]
    script = Path(sys.executable).parent / ("qdrant-memory-mcp.exe" if sys.platform == "win32" else "qdrant-memory-mcp")
    result = subprocess.run([str(script), "--help"], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "mcp" in result.stdout
