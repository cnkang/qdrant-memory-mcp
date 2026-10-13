"""Inspect/download immutable PyPI artifacts and verify public ownership metadata."""

import argparse
import hashlib
import json
import os
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path


def release(project, required):
    url = f"https://pypi.org/pypi/{project['name']}/{project['version']}/json"
    for attempt in range(12 if required else 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            if not required:
                return None
            if attempt < 11:
                time.sleep(5)
    raise RuntimeError("Required PyPI version is not available")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require", action="store_true")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    data = release(project, args.require)
    exists = data is not None
    if exists:
        info = data["info"]
        assert info["name"] == project["name"] and info["version"] == project["version"]
        assert "<!-- mcp-name: io.github.cnkang/qdrant-memory -->" in info["description"]
        assert info["requires_dist"] == project["dependencies"]
        urls = data["urls"]
        assert len(urls) == 2 and {u["packagetype"] for u in urls} == {"bdist_wheel", "sdist"}
        for item in urls:
            assert not item["yanked"]
            filename = item["filename"]
            assert Path(filename).name == filename
            assert item["url"].startswith("https://files.pythonhosted.org/")
            with urllib.request.urlopen(item["url"], timeout=30) as response:
                payload = response.read()
            assert hashlib.sha256(payload).hexdigest() == item["digests"]["sha256"]
            if args.download:
                Path("dist").mkdir(exist_ok=True)
                Path("dist", filename).write_bytes(payload)
            else:
                assert Path("dist", filename).read_bytes() == payload, f"Conflicting immutable artifact: {filename}"
        wheel_path = next(Path("dist").glob("*.whl"))
        with zipfile.ZipFile(wheel_path) as wheel:
            assert all(".dist-info/" in name for name in wheel.namelist())
            entry = wheel.read(next(n for n in wheel.namelist() if n.endswith("/entry_points.txt"))).decode()
            assert "qdrant-memory-mcp = qdrant_memory.standalone:main" in entry
            metadata = BytesParser().parsebytes(wheel.read(next(n for n in wheel.namelist() if n.endswith("/METADATA"))))
            assert metadata["Version"] == project["version"]
            assert metadata.get_all("Requires-Dist") == project["dependencies"]
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"exists={str(exists).lower()}\n")
    print(f"Public PyPI release verified: {exists}")


if __name__ == "__main__":
    main()
