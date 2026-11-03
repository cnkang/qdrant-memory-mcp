"""The download path verifies both artifacts before it writes them."""

import hashlib
import importlib.util
import io
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheel_bytes(project):
    buffer = io.BytesIO()
    metadata = ["Metadata-Version: 2.1", f"Name: {project['name']}", f"Version: {project['version']}"]
    metadata += [f"Requires-Dist: {item}" for item in project["dependencies"]]
    for group, deps in project.get("optional-dependencies", {}).items():
        metadata += [f'Requires-Dist: {item}; extra == "{group}"' for item in deps]
    metadata.append("Description-Content-Type: text/markdown")
    metadata.append("")
    metadata.append("<!-- mcp-name: io.github.cnkang/qdrant-memory -->")
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("qdrant_memory_mcp-0.2.9.dist-info/METADATA", "\n".join(metadata) + "\n")
        archive.writestr(
            "qdrant_memory_mcp-0.2.9.dist-info/entry_points.txt",
            "[console_scripts]\nqdrant-memory-mcp = qdrant_memory.standalone:main\n",
        )
        archive.writestr("qdrant_memory_mcp-0.2.9.dist-info/RECORD", "")
    return buffer.getvalue()


@pytest.fixture
def release_project(tmp_path, monkeypatch):
    """A project tree whose artifacts match what the payload claims."""
    module = load("pypi_release")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    (tmp_path / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    monkeypatch.chdir(tmp_path)
    wheel = wheel_bytes(metadata)
    sdist = b"immutable source archive"
    files = {
        f"{metadata['name'].replace('-', '_')}-{metadata['version']}-py3-none-any.whl": wheel,
        f"{metadata['name'].replace('-', '_')}-{metadata['version']}.tar.gz": sdist,
    }
    payload = {
        "info": {
            "name": metadata["name"],
            "version": metadata["version"],
            "description": "<!-- mcp-name: io.github.cnkang/qdrant-memory -->",
            "requires_dist": module.expected_requirements(metadata),
        },
        "urls": [
            {
                "packagetype": "bdist_wheel" if name.endswith(".whl") else "sdist",
                "filename": name,
                "yanked": False,
                "url": f"https://files.pythonhosted.org/packages/ab/cd/{name}",
                "digests": {"sha256": hashlib.sha256(data).hexdigest()},
            }
            for name, data in files.items()
        ],
    }
    monkeypatch.setattr(module, "release", lambda project, required: payload)

    def download(url, timeout=30):
        for name, data in files.items():
            if url.endswith(name):
                return io.BytesIO(data)
        raise AssertionError(f"unexpected download: {url}")

    monkeypatch.setattr(module.urllib.request, "urlopen", download)
    return module, files


def test_download_writes_both_verified_artifacts(release_project, tmp_path, monkeypatch):
    module, files = release_project
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr("sys.argv", ["pypi_release.py", "--download"])

    module.main()

    for name, data in files.items():
        assert (tmp_path / "dist" / name).read_bytes() == data
    assert "exists=true" in output.read_text(encoding="utf-8")


def test_verify_only_reads_the_local_artifacts(release_project, tmp_path, monkeypatch):
    module, files = release_project
    (tmp_path / "dist").mkdir()
    for name, data in files.items():
        (tmp_path / "dist" / name).write_bytes(data)
    monkeypatch.setattr("sys.argv", ["pypi_release.py"])

    module.main()

    assert sorted(path.name for path in (tmp_path / "dist").iterdir()) == sorted(files)


def test_a_conflicting_local_artifact_is_rejected(release_project, tmp_path, monkeypatch):
    module, files = release_project
    (tmp_path / "dist").mkdir()
    for name in files:
        (tmp_path / "dist" / name).write_bytes(b"different bytes")
    monkeypatch.setattr("sys.argv", ["pypi_release.py"])

    with pytest.raises(AssertionError):
        module.main()


def test_an_artifact_that_fails_its_digest_is_not_written(release_project, tmp_path, monkeypatch):
    module, _ = release_project
    payload = module.release(None, False)
    payload["urls"][0]["digests"]["sha256"] = "0" * 64
    monkeypatch.setattr("sys.argv", ["pypi_release.py", "--download"])

    with pytest.raises(AssertionError):
        module.main()
    assert not (tmp_path / "dist").exists() or not any((tmp_path / "dist").iterdir())


def test_a_yanked_artifact_is_rejected(release_project, monkeypatch):
    module, _ = release_project
    payload = module.release(None, False)
    for item in payload["urls"]:
        item["yanked"] = True
    monkeypatch.setattr("sys.argv", ["pypi_release.py"])

    with pytest.raises(AssertionError):
        module.main()


def test_an_absent_release_reports_exists_false(release_project, tmp_path, monkeypatch):
    module, _ = release_project
    monkeypatch.setattr(module, "release", lambda project, required: None)
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr("sys.argv", ["pypi_release.py"])

    module.main()

    assert "exists=false" in output.read_text(encoding="utf-8")

