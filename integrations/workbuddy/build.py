#!/usr/bin/env python3
"""Package the existing stdio distribution and immutable upstream WorkBuddy Skill."""

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "qdrant-memory-workbuddy/"
SEMVER = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


def validate_metadata(meta):
    required = {"name", "name_zh", "name_en", "description", "description_zh", "description_en", "source", "type", "version", "minWorkbuddyVersion", "examples_zh", "examples_en"}
    if not isinstance(meta, dict) or set(meta) != required:
        raise ValueError("Connector metadata fields differ from reviewed MVP schema")
    if not all(isinstance(meta[k], str) and meta[k].strip() for k in required - {"examples_zh", "examples_en"}):
        raise ValueError("Metadata text must be nonempty strings")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", meta["source"]) or meta["type"] != "mcp":
        raise ValueError("Invalid connector source or type")
    if not re.fullmatch(SEMVER, meta["version"]) or meta["minWorkbuddyVersion"] != "4.24.0":
        raise ValueError("Invalid connector version or minimum client version")
    for key in ("examples_zh", "examples_en"):
        if not isinstance(meta[key], list) or not 2 <= len(meta[key]) <= 5 or not all(isinstance(x, str) and x.strip() for x in meta[key]):
            raise ValueError("Provide 2-5 bilingual examples")
    if not all(re.search(r"[\u3400-\u9fff]", meta[k]) for k in ("name_zh", "description_zh")):
        raise ValueError("Chinese metadata required")


def validate_mcp(mcp, version):
    expected = {"mcpServers": {"qdrant-memory": {"type": "stdio", "command": "uvx", "args": ["--from", f"qdrant-memory-mcp=={version}", "qdrant-memory-mcp", "mcp"], "timeout": 30000}}}
    if mcp != expected:
        raise ValueError("MCP must use the single reviewed uvx stdio server; no token/runtime claims")


def inputs(root):
    adapter = root / "integrations/workbuddy"
    def read(name):
        path = adapter / name
        if path.is_symlink():
            raise ValueError("Adapter input symlink forbidden")
        return json.loads(path.read_text(encoding="utf-8"))
    meta, mcp, source = (read(name) for name in ("connector-meta.json", "mcp.json", "skill-source.json"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    runtime = json.loads((root / "runtime-source.json").read_text(encoding="utf-8"))
    validate_metadata(meta)
    # Version is generated from the package for future tags. The checked-in
    # example pin must match the current project as well.
    validate_mcp(mcp, project["version"])
    if project["dependencies"] != [f"hermes-plugin-qdrant-memory[mcp]=={runtime['version']}"]:
        raise ValueError("Runtime dependency and provenance mismatch")
    if set(source) != {"repository", "commit", "version"} or source["repository"] != "https://github.com/cnkang/skills.git" or not re.fullmatch(r"[0-9a-f]{40}", source["commit"]) or not re.fullmatch(SEMVER, source["version"]):
        raise ValueError("Skill must come from immutable canonical repository")
    return meta, mcp, source, project, runtime


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def validate_skill_source(skill_root, source):
    if git(skill_root, "remote", "get-url", "origin") not in {source["repository"], "https://github.com/cnkang/skills", "git@github.com:cnkang/skills.git"}:
        raise ValueError("Skill origin differs from canonical repository")
    if git(skill_root, "rev-parse", "HEAD") != source["commit"]:
        raise ValueError("Skill checkout must match the full pinned commit")
    if git(skill_root, "status", "--porcelain", "--ignored"):
        raise ValueError("Skill checkout must be clean, including ignored files; use a fresh clone")


def safe_resource(name):
    path = PurePosixPath(name)
    if path.is_absolute() or "\\" in name or ".." in path.parts or not path.parts or path.parts[0] != "qdrant-memory":
        return False
    parts = path.parts[1:]
    if not parts or any(p.startswith(".") or p in {"__pycache__", "node_modules", "secrets", "venv"} for p in parts):
        return False
    if any(word in path.stem.lower() for word in ("secret", "credential", "private-key")):
        return False
    return (len(parts) == 1 and parts[0] in {"SKILL.md", "LICENSE", "README.md", "requirements.txt"}) or (parts[0] in {"references", "scripts", "assets", "agents", "examples", "templates", "tests"} and path.suffix in {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".txt", ".svg"})


def skill_files(skill_root, source):
    validate_skill_source(skill_root, source)
    with tempfile.TemporaryDirectory() as temp:
        # Reuse, never reimplement, upstream frontmatter/link/resource validation.
        subprocess.run([sys.executable, "-B", str(skill_root / "integrations/workbuddy/build.py"), "--skill", "qdrant-memory", "--output-dir", str(Path(temp).resolve())], check=True, capture_output=True)
        archives = list(Path(temp).glob("*.zip"))
        if len(archives) != 1:
            raise ValueError("Upstream must build exactly one Skill")
        with zipfile.ZipFile(archives[0]) as archive:
            entries = archive.infolist()
            if len({x.filename for x in entries}) != len(entries) or archive.testzip():
                raise ValueError("Invalid upstream archive")
            files = {}
            for entry in entries:
                mode = entry.external_attr >> 16
                if not safe_resource(entry.filename) or not stat.S_ISREG(mode):
                    raise ValueError("Unsafe upstream resource")
                files["skills/" + entry.filename] = (archive.read(entry), stat.S_IMODE(mode))
    raw = files["skills/qdrant-memory/SKILL.md"][0]
    canonical = subprocess.check_output(["git", "-C", str(skill_root), "show", "HEAD:qdrant-memory/SKILL.md"])
    if raw.split(b"\n---\n", 1)[1] != canonical.split(b"\n---\n", 1)[1]:
        raise ValueError("Canonical Skill body differs")
    # Top-level version is emitted by the reviewed upstream adapter.
    header = raw.split(b"\n---\n", 1)[0].decode("utf-8")
    if not re.search(r"(?m)^version: ['\"]?" + re.escape(source["version"]) + r"['\"]?$", header):
        raise ValueError("Skill version mismatch")
    if "skills/qdrant-memory/LICENSE" not in files:
        raise ValueError("Skill license missing")
    return files


def archive_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, (content, mode) in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, content)
    return stream.getvalue()


def write_once(path, content):
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Output symlink forbidden")
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ValueError("Refusing to overwrite different output")


def package_name(connector, mcp, release_tag):
    if release_tag is not None and release_tag != "v" + mcp:
        raise ValueError("Release tag must match package version")
    suffix = "" if release_tag else "-preview"
    return f"qdrant-memory-workbuddy-connector-v{connector}-mcp-v{mcp}{suffix}.zip"


def build(root, skill_root, output, release_tag=None):
    meta, mcp, source, project, runtime = inputs(root)
    name = package_name(meta["version"], project["version"], release_tag)
    files = skill_files(skill_root, source)
    provenance = {"connector_version": meta["version"], "mcp_version": project["version"], "runtime_version": runtime["version"], "skill_version": source["version"], "skill_repository": source["repository"], "skill_commit": source["commit"], "release_tag": release_tag}
    for filename, value in (("connector-meta.json", meta), ("mcp.json", mcp), ("provenance.json", provenance)):
        files[filename] = ((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(), 0o644)
    icon = root / "integrations/workbuddy/icon.svg"
    if icon.is_symlink():
        raise ValueError("Invalid icon")
    # SVG is text; normalize Git checkout LF/CRLF translation just as JSON
    # inputs are normalized during parsing. Skill resources use Git blobs.
    icon_bytes = icon.read_text(encoding="utf-8").encode("utf-8")
    if b"<svg" not in icon_bytes or b"<script" in icon_bytes:
        raise ValueError("Invalid icon")
    files["icon.svg"] = (icon_bytes, 0o644)
    files = {PREFIX + key: value for key, value in files.items()}
    data = archive_bytes(files)
    output = output.absolute()
    if any(p.is_symlink() for p in [output, *output.parents]):
        raise ValueError("Output symlink forbidden")
    if output.is_relative_to(root.resolve()) and output != root.resolve() / "dist/workbuddy":
        raise ValueError("Repository output must be dist/workbuddy")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / name
    checksum = archive.with_suffix(".zip.sha256")
    write_once(archive, data)
    write_once(checksum, f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode())
    return archive, checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=ROOT / ".workbuddy-skill")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/workbuddy")
    parser.add_argument("--release-tag")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            paths = build(ROOT, args.skill_root, Path(one).resolve(), args.release_tag)
            repeated = build(ROOT, args.skill_root, Path(two).resolve(), args.release_tag)
            if any(a.read_bytes() != b.read_bytes() for a, b in zip(paths, repeated)):
                raise ValueError("Build is not reproducible")
        print("Connector metadata, provenance, Skill resources and deterministic checksum verified")
    else:
        for path in build(ROOT, args.skill_root, args.output_dir, args.release_tag):
            print(path)


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        # Our validation messages are static and never contain user data.
        raise SystemExit(f"WorkBuddy build failed: {exc}")
    except (OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        raise SystemExit(f"WorkBuddy build failed ({type(exc).__name__}); inspect reviewed inputs, not user profiles")
