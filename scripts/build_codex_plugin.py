"""Validate and deterministically package the portable Codex plugin; never publish."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = "plugins/qdrant-memory"
VERIFICATION_PATH = "docs/codex-plugin-verification.md"
PLUGIN = ROOT / PLUGIN_PATH


def git(repo, *args):
    directory = Path(repo).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Git repository must be a directory")
    fixed = {
        ("rev-parse", "HEAD"),
        (
            "status",
            "--porcelain",
            "--",
            "plugins",
            "scripts/build_codex_plugin.py",
            VERIFICATION_PATH,
        ),
        ("ls-files", "-z", "--", PLUGIN_PATH),
    }
    archive = (
        len(args) == 3
        and args[0] == "archive"
        and re.fullmatch(r"[0-9a-f]{40}", args[1])
        and args[2] == "qdrant-memory"
    )
    if args not in fixed and not archive:
        raise ValueError("Unsupported plugin build Git operation")
    return subprocess.check_output(["git", *args], cwd=directory)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(root=PLUGIN):
    """Apply offline invariants; optional official schema validation is separate."""
    manifest = json.loads((root / "plugin.json").read_text())
    mcp = json.loads((root / "mcp.json").read_text())
    require(manifest["name"] == "qdrant-memory", "Invalid plugin name")
    require(manifest["version"] == "0.1.1", "Invalid plugin version")
    require(
        not {"skills", "mcpServers", "apps", "interface"} & manifest.keys(),
        "Invalid manifest fields",
    )
    extension = manifest["extensions"]["com.openai"]
    require(
        extension["onboardingSkill"] == "./skills/setup/SKILL.md",
        "Invalid onboarding skill",
    )
    require(
        len(extension["interface"]["shortDescription"]) <= 30, "Description too long"
    )
    require(extension["interface"]["category"] == "Productivity", "Invalid category")
    overlay = json.loads((root / ".codex-plugin/plugin.json").read_text())
    require(
        all(
            overlay[key] == manifest[key] for key in ("name", "version", "description")
        ),
        "Compatibility manifest mismatch",
    )
    require(
        overlay["extensions"]["com.openai"]["onboardingSkill"]
        == extension["onboardingSkill"],
        "Compatibility onboarding mismatch",
    )
    require(not (root / ".mcp.json").exists(), "Unsupported MCP manifest")
    server = mcp["mcpServers"]["qdrant-memory"]
    compatible = dict(overlay["mcpServers"]["qdrant-memory"])
    require(
        set(compatible.pop("env_vars"))
        == {
            "QDRANT_MEMORY_CODEX_ROOT",
            "QDRANT_MEMORY_CODEX_PROFILE",
            "QDRANT_MEMORY_CODEX_EXECUTABLE",
            "QDRANT_MEMORY_CODEX_OWNER_URL",
            "QDRANT_MEMORY_SHARED_TOKEN",
            "QDRANT_API_KEY",
            "EMBEDDING_API_KEY",
        },
        "Invalid environment passthrough",
    )
    require(compatible == server, "Compatibility MCP mismatch")
    require(
        server
        == {
            "type": "stdio",
            "command": "node",
            "args": ["${PLUGIN_ROOT}/launcher.mjs", "mcp"],
            "cwd": "${PLUGIN_ROOT}",
        },
        "Invalid MCP command",
    )
    for name in ("setup", "memory-migration", "memory-backup", "qdrant-memory"):
        text = (root / "skills" / name / "SKILL.md").read_text()
        require(
            text.startswith("---\n") and f"name: {name}\n" in text,
            "Invalid skill: " + name,
        )
    return manifest


def source_files():
    """Read only tracked plugin files, rejecting symbolic links."""
    files = {}
    for name in sorted(
        git(ROOT, "ls-files", "-z", "--", PLUGIN_PATH).decode().split("\0")
    ):
        if not name:
            continue
        path = ROOT / name
        parts = PurePosixPath(name).parts
        if any(
            ROOT.joinpath(*parts[:index]).is_symlink()
            for index in range(1, len(parts) + 1)
        ):
            raise ValueError("Plugin source cannot contain symlinks")
        if path.is_file():
            files[str(path.relative_to(PLUGIN)).replace("\\", "/")] = path.read_bytes()
    return files


def skill_files(skill_repo, commit):
    """Read the pinned skill archive without extracting paths to disk."""
    files = {}
    snapshot = git(skill_repo, "archive", commit, "qdrant-memory")
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
    require(
        "skills/qdrant-memory/SKILL.md" in files, "Pinned upstream skill lacks SKILL.md"
    )
    return files


def build(output, skill_repo):
    """Bundle a precise upstream skill snapshot and content integrity manifest."""
    validate(PLUGIN)
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
            VERIFICATION_PATH,
        )
    )
    files = source_files()
    files.update(skill_files(skill_repo, release["skill_commit"]))
    files["release.json"] = json.dumps(release, indent=2).encode() + b"\n"
    files["VERIFICATION.md"] = (ROOT / VERIFICATION_PATH).read_bytes()
    # Account hosts normalize publisher/compatibility metadata. The archive SHA
    # covers the complete source ZIP; immutable component hashes also survive
    # that host normalization.
    mutable_manifests = {"plugin.json", ".codex-plugin/plugin.json"}
    integrity = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(files.items())
        if name not in mutable_manifests
    }
    files["integrity.json"] = (
        json.dumps(
            {
                "format": "qdrant-plugin-components",
                "version": 1,
                "host_normalized_manifests": sorted(mutable_manifests),
                "files": integrity,
            },
            indent=2,
        ).encode()
        + b"\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("qdrant-memory/" + name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output) as archive:
        require(archive.testzip() is None, "Corrupt plugin archive")
        for name, checksum in integrity.items():
            require(
                hashlib.sha256(archive.read("qdrant-memory/" + name)).hexdigest()
                == checksum,
                "Archive checksum mismatch: " + name,
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
        "--output", type=Path, default=ROOT / "dist/qdrant-memory-codex-0.1.1.zip"
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
