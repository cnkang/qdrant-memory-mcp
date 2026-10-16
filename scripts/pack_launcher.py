"""Build and inspect the npm launcher archive without publishing it."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "package.json", "launcher.mjs", "provision.mjs", "bridge.mjs", "bootstrap.mjs",
    "tools.json", "runtime.json", "requirements.in", "requirements.lock",
    "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
}


def inspect(archive, source):
    """Require the exact reviewed payload, license and executable entry point."""
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        expected = {"package/" + name for name in FILES}
        if len(members) != len(expected) or {m.name for m in members} != expected:
            raise ValueError("Unexpected launcher package contents")
        for member in members:
            if not member.isfile() or member.size > 4 * 1024 * 1024:
                raise ValueError("Launcher payload must contain bounded regular files")
            path = source / member.name.removeprefix("package/")
            if path.is_symlink() or not path.is_file():
                raise ValueError("Launcher input must be a regular file")
            if package.extractfile(member).read() != path.read_bytes():
                raise ValueError("Launcher package differs from source")
            if member.name == "package/launcher.mjs" and not member.mode & stat.S_IXUSR:
                raise ValueError("Launcher CLI must be executable")
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
    source = ROOT / "integrations/managed"
    output = args.output_dir.absolute()
    if output.is_relative_to(ROOT) and output != ROOT / "dist/launcher":
        raise ValueError("Repository output must be dist/launcher")
    if any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError("Output symlink forbidden")
    output.mkdir(parents=True, exist_ok=True)
    # Pack in a fresh destination: never replace an existing release artifact.
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    if (output / filename).exists():
        raise ValueError("Package already exists; choose a fresh output directory")
    # Keep user paths out of command arguments, including Windows .cmd parsing.
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
