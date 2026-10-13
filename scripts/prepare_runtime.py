"""Build a pinned candidate wheel for preparation CI only; never publish it."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "runtime-source.json").read_text())
    sha = source["commit"]
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
    target = root / ".runtime"
    subprocess.run(["git", "clone", "--no-checkout", source["repository"], str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", sha], check=True)
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(root / ".runtime-dist"), str(target)], check=True)
    print(f"Preparation-only Runtime wheel from immutable source {sha}")


if __name__ == "__main__":
    main()
