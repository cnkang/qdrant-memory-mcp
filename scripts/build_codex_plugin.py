"""Validate and deterministically package the portable Codex plugin; never publish."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/qdrant-memory"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def validate(root=PLUGIN):
    """Apply offline invariants; optional official schema validation is separate."""
    manifest = json.loads((root / "plugin.json").read_text())
    mcp = json.loads((root / "mcp.json").read_text())
    assert manifest["name"] == "qdrant-memory"
    assert manifest["version"] == "0.1.0"
    assert not {"skills", "mcpServers", "apps", "interface"} & manifest.keys()
    extension = manifest["extensions"]["com.openai"]
    assert extension["onboardingSkill"] == "./skills/setup/SKILL.md"
    assert len(extension["interface"]["shortDescription"]) <= 30
    assert extension["interface"]["category"] == "Productivity"
    overlay = json.loads((root / ".codex-plugin/plugin.json").read_text())
    assert all(
        overlay[key] == manifest[key] for key in ("name", "version", "description")
    )
    assert (
        overlay["extensions"]["com.openai"]["onboardingSkill"]
        == extension["onboardingSkill"]
    )
    assert not (root / ".mcp.json").exists()
    server = mcp["mcpServers"]["qdrant-memory"]
    compatible = dict(overlay["mcpServers"]["qdrant-memory"])
    assert set(compatible.pop("env_vars")) == {
        "QDRANT_MEMORY_CODEX_ROOT",
        "QDRANT_MEMORY_CODEX_PROFILE",
        "QDRANT_MEMORY_CODEX_EXECUTABLE",
        "QDRANT_MEMORY_CODEX_OWNER_URL",
        "QDRANT_MEMORY_SHARED_TOKEN",
        "QDRANT_API_KEY",
        "EMBEDDING_API_KEY",
    }
    assert compatible == server
    assert server == {
        "type": "stdio",
        "command": "node",
        "args": ["${PLUGIN_ROOT}/launcher.mjs", "mcp"],
        "cwd": "${PLUGIN_ROOT}",
    }
    for name in ("setup", "memory-migration", "memory-backup", "qdrant-memory"):
        text = (root / "skills" / name / "SKILL.md").read_text()
        assert text.startswith("---\n") and f"name: {name}\n" in text
    return manifest


def build(output, skill_repo):
    """Bundle a precise upstream skill snapshot and content integrity manifest."""
    validate()
    release = json.loads((PLUGIN / "release.json").read_text())
    release["plugin_source_commit"] = git(ROOT, "rev-parse", "HEAD").decode().strip()
    release["source_dirty"] = bool(
        git(
            ROOT,
            "status",
            "--porcelain",
            "--",
            "plugins",
            "scripts/build_codex_plugin.py",
        )
    )
    files = {}
    for path in sorted(PLUGIN.rglob("*")):
        if path.is_symlink():
            raise ValueError("Plugin source cannot contain symlinks")
        if path.is_file():
            files[str(path.relative_to(PLUGIN)).replace("\\", "/")] = path.read_bytes()
    snapshot = git(skill_repo, "archive", release["skill_commit"], "qdrant-memory")
    with tarfile.open(fileobj=io.BytesIO(snapshot)) as archive:
        for member in archive:
            if member.isdir():
                continue
            path = PurePosixPath(member.name)
            if not member.isfile() or ".." in path.parts or path.is_absolute():
                raise ValueError("Unsafe upstream skill archive")
            relative = path.relative_to("qdrant-memory")
            if "__pycache__" not in relative.parts:
                files["skills/qdrant-memory/" + str(relative)] = archive.extractfile(
                    member
                ).read()
    files["release.json"] = json.dumps(release, indent=2).encode() + b"\n"
    integrity = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())
    }
    files["integrity.json"] = json.dumps(integrity, indent=2).encode() + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("qdrant-memory/" + name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name, checksum in integrity.items():
            assert (
                hashlib.sha256(archive.read("qdrant-memory/" + name)).hexdigest()
                == checksum
            )
    return {
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "files": len(files),
        "source_dirty": release["source_dirty"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/qdrant-memory-codex-0.1.0.zip"
    )
    parser.add_argument("--skill-repo", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        validate()
        print(json.dumps({"ok": True, "validation": "offline package invariants"}))
    else:
        if args.skill_repo is None:
            parser.error("--skill-repo must contain the pinned upstream commit")
        print(json.dumps(build(args.output, args.skill_repo)))


if __name__ == "__main__":
    main()
