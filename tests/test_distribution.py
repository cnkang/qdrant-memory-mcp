"""Assert the installable distribution remains a metadata-only upstream adapter."""

import configparser
import importlib.metadata
import json
import subprocess
import sysconfig
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_metadata_verification_is_independent_of_windows_codepage(monkeypatch):
    """Ensure UTF-8 metadata checks do not inherit Windows locale decoding."""
    from test_release_guards import load_script

    read = Path.read_text

    def legacy_windows_read(path, *args, **kwargs):
        """Simulate cp1252 unless the reader explicitly selects an encoding."""
        kwargs.setdefault("encoding", "cp1252")
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", legacy_windows_read)
    load_script("verify_metadata").verify()


def test_metadata_contract():
    """Keep dependency, Registry versions and ownership aligned with packaging."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    server = json.loads((ROOT / "server.json").read_text())
    assert project["dependencies"] == ["hermes-plugin-qdrant-memory[mcp]==0.5.1"]
    assert project["scripts"] == {"qdrant-memory-mcp": "qdrant_memory.standalone:main"}
    assert project["version"] == server["version"] == server["packages"][0]["version"]
    assert server["packages"][0]["identifier"] == project["name"]
    marker = f"<!-- mcp-name: {server['name']} -->"
    assert marker in (ROOT / "README.md").read_text()
    assert not (ROOT / "qdrant_memory").exists()
    paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]).decode().split("\0")
    assert not any(Path(p).name == "SKILL.md" for p in paths)


def test_artifacts_are_metadata_only():
    """Reject business code and internal plans in wheel and source archives."""
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        assert all(".dist-info/" in name for name in names)
        metadata = BytesParser().parsebytes(
            wheel.read(next(n for n in names if n.endswith("/METADATA")))
        )
        assert (
            "<!-- mcp-name: io.github.cnkang/qdrant-memory -->"
            in metadata.get_payload()
        )
        requires = metadata.get_all("Requires-Dist") or []
        from test_release_guards import load_script

        release = load_script("pypi_release")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        # The public release check must expect exactly what the wheel declares,
        # including the markers of the declared optional extras.
        assert sorted(release.requirement_key(r) for r in requires) == sorted(
            release.requirement_key(r) for r in release.expected_requirements(project)
        )
        entry = configparser.ConfigParser()
        entry.read_string(
            wheel.read(
                next(n for n in names if n.endswith("entry_points.txt"))
            ).decode()
        )
        assert (
            entry["console_scripts"]["qdrant-memory-mcp"]
            == "qdrant_memory.standalone:main"
        )
    with tarfile.open(sdists[0]) as archive:
        assert not any("/docs/superpowers/" in n for n in archive.getnames())
        assert not any(
            "/qdrant_memory/" in n or n.endswith("/SKILL.md")
            for n in archive.getnames()
        )


def test_installed_entrypoint():
    """Verify installed distribution provenance and the delegated console command."""
    dist = importlib.metadata.distribution("qdrant-memory-mcp")
    assert dist.version == "0.2.5"
    runtime = importlib.metadata.distribution("hermes-plugin-qdrant-memory")
    assert runtime.version == "0.5.1"
    assert importlib.metadata.packages_distributions()["qdrant_memory"] == [
        "hermes-plugin-qdrant-memory"
    ]
    # Resolve the installed console script through sysconfig: on Windows the
    # scripts live in a Scripts/ subdirectory, unlike POSIX prefixes.
    script = Path(sysconfig.get_path("scripts")) / (
        "qdrant-memory-mcp.exe" if sys.platform == "win32" else "qdrant-memory-mcp"
    )
    result = subprocess.run(
        [str(script), "--help"], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert "mcp" in result.stdout
