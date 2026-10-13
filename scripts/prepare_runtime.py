"""Build a pinned candidate wheel for preparation CI only; never publish it."""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "runtime-source.json").read_text())
    artifacts = root / ".runtime-dist"
    artifacts.mkdir(exist_ok=True)
    version = source["version"]
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/hermes-plugin-qdrant-memory/{version}/json", timeout=30) as response:
            json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    else:
        subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:", "--dest", str(artifacts), f"hermes-plugin-qdrant-memory=={version}"], check=True)
        print(f"Use public immutable Runtime {version}; no source fallback needed")
        return
    sha = source["commit"]
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
    target = root / ".runtime"
    subprocess.run(["git", "clone", "--no-checkout", source["repository"], str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", sha], check=True)
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(artifacts), str(target)], check=True)
    print(f"Preparation-only Runtime wheel from immutable source {sha}")


if __name__ == "__main__":
    main()
