"""Build and inspect the DSH bundle archive without publishing it."""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {"package.json", "cordis.patch.yml", "README.md", "LICENSE"}


def inspect(archive, source):
    """Require the exact reviewed payload and a valid dsh.bundle manifest."""
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        expected = {"package/" + name for name in FILES}
        if len(members) != len(expected) or {m.name for m in members} != expected:
            raise ValueError("Unexpected bundle package contents")
        for member in members:
            if not member.isfile() or member.size > 1024 * 1024:
                raise ValueError("Bundle payload must contain bounded regular files")
            path = source / member.name.removeprefix("package/")
            if path.is_symlink() or not path.is_file():
                raise ValueError("Bundle input must be a regular file")
            if package.extractfile(member).read() != path.read_bytes():
                raise ValueError("Bundle package differs from source")
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    if meta.get("dsh", {}).get("bundle", {}).get("patch") != "./cordis.patch.yml":
        raise ValueError("Bundle manifest must declare the reviewed patch file")
    if meta.get("private"):
        raise ValueError("Published bundle must not be private")
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def normalize(report):
    """Accept both npm pack --json shapes: one array item or one keyed entry."""
    if isinstance(report, dict):
        values = list(report.values())
        if len(values) != 1 or not isinstance(values[0], dict):
            raise ValueError("Unexpected npm pack report")
        return values[0]
    packed, = report
    return packed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = ROOT / "integrations/dsh/bundle"
    output = args.output_dir.absolute()
    if output.is_relative_to(ROOT) and output != ROOT / "dist/dsh-bundle":
        raise ValueError("Repository output must be dist/dsh-bundle")
    if any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError("Output symlink forbidden")
    output.mkdir(parents=True, exist_ok=True)
    # Pack in a fresh destination: never replace an existing release artifact.
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    if (output / filename).exists():
        raise ValueError("Package already exists; choose a fresh output directory")
    env = {**os.environ, "npm_config_pack_destination": str(output)}
    if os.name == "nt":
        raw = subprocess.check_output(["npm.cmd", "pack", "--json", "--ignore-scripts"], cwd=source, env=env, text=True, timeout=120)
    else:
        raw = subprocess.check_output(["npm", "pack", "--json", "--ignore-scripts"], cwd=source, env=env, text=True, timeout=120)
    packed = normalize(json.loads(raw))
    if packed["filename"] != filename:
        raise ValueError("Unexpected npm package identity")
    archive = output / filename
    print(json.dumps({"archive": str(archive), "sha256": inspect(archive, source), "integrity": packed["integrity"]}))


if __name__ == "__main__":
    main()
