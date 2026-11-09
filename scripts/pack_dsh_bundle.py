"""Build and inspect the DSH bundle archive without publishing it."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = "package.json"
FILES = {PACKAGE_JSON, "cordis.patch.yml", "README.md", "LICENSE", "index.js", "native/index.js"}
PAYLOAD_LIMIT = 1024 * 1024


def bounded_bytes(source, name):
    """Read one reviewed payload file within the bounded inspection size."""
    path = payload_path(source, name)
    if path.stat().st_size > PAYLOAD_LIMIT:
        raise ValueError('Bundle input exceeds the bounded payload size')
    return path.read_bytes()


def validate_identity(meta):
    """Reject path-bearing identities before deriving an output filename."""
    if meta.get('name') != '@cnkang/qdrant-memory-dsh-bundle' or not re.fullmatch(
        r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-rc\.[1-9]\d*)?',
        meta.get('version', ''), re.ASCII,
    ):
        raise ValueError('Unexpected bundle package identity')


def payload_path(source, name):
    """Map the single canonical Native source into the reviewed bundle payload."""
    path = source.parent / 'native/index.js' if name == 'native/index.js' else source / name
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError('Bundle input symlink forbidden')
    return path


def inspect(archive, source):
    """Require the exact reviewed payload and a valid dsh.bundle manifest."""
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        expected = {"package/" + name for name in FILES}
        if len(members) != len(expected) or {m.name for m in members} != expected:
            raise ValueError("Unexpected bundle package contents")
        for member in members:
            if not member.isfile() or member.size > PAYLOAD_LIMIT:
                raise ValueError("Bundle payload must contain bounded regular files")
            path = payload_path(source, member.name.removeprefix("package/"))
            if path.is_symlink() or not path.is_file():
                raise ValueError("Bundle input must be a regular file")
            if package.extractfile(member).read() != path.read_bytes():
                raise ValueError("Bundle package differs from source")
    meta = json.loads((source / PACKAGE_JSON).read_text(encoding="utf-8"))
    if meta.get("dsh", {}).get("bundle", {}).get("patch") != "./cordis.patch.yml":
        raise ValueError("Bundle manifest must declare the reviewed patch file")
    if meta.get("private"):
        raise ValueError("Published bundle must not be private")
    validate_identity(meta)
    if meta.get('main') != './index.js' or meta.get('imports') != {'#qdrant-native': './native/index.js'}:
        raise ValueError('Unexpected bundle Host module')
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
    meta = json.loads(bounded_bytes(source, PACKAGE_JSON))
    validate_identity(meta)
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    if (output / filename).exists():
        raise ValueError("Package already exists; choose a fresh output directory")
    env = {**os.environ, "npm_config_pack_destination": str(output)}
    with tempfile.TemporaryDirectory(prefix='qdrant-dsh-pack-') as temporary:
        stage = Path(temporary)
        for name in sorted(FILES):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bounded_bytes(source, name))
        raw = subprocess.check_output(
            ['npm.cmd' if os.name == 'nt' else 'npm', 'pack', '--json', '--ignore-scripts'],
            cwd=stage, env=env, text=True, timeout=120,
        )
    packed = normalize(json.loads(raw))
    if packed["filename"] != filename:
        raise ValueError("Unexpected npm package identity")
    archive = output / filename
    print(json.dumps({"archive": str(archive), "sha256": inspect(archive, source), "integrity": packed["integrity"]}))


if __name__ == "__main__":
    main()
