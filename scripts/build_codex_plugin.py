"""Validate and deterministically package the portable Codex plugin; never publish."""

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from contextlib import ExitStack
from functools import cache

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


_TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def _normalize_text_bytes(name, data):
    """Make packaged UTF-8 text independent of checkout/archive EOL rules."""
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.suffix.lower() not in _TEXT_SUFFIXES and path.name.upper() not in {
        "COPYING",
        "LICENSE",
        "NOTICE",
    }:
        return data
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Packaged text source is not UTF-8: " + str(name)) from error
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def validate(root=PLUGIN, files=None):
    """Apply offline invariants; optional official schema validation is separate."""

    def read(name):
        if files is None:
            return (root / name).read_text(encoding="utf-8")
        require(name in files, "Missing plugin file: " + name)
        return files[name].decode("utf-8")

    manifest = json.loads(read("plugin.json"))
    mcp = json.loads(read("mcp.json"))
    require(manifest["name"] == "qdrant-memory", "Invalid plugin name")
    require(manifest["version"] == "0.1.4", "Invalid plugin version")
    require(
        not {"skills", "mcpServers", "apps", "interface"} & manifest.keys(),
        "Invalid manifest fields",
    )
    extensions = manifest.get("extensions", {})
    require(isinstance(extensions, dict), "Invalid root extensions")
    inline_extension = extensions.get("com.openai")
    require(
        inline_extension is None or isinstance(inline_extension, dict),
        "Invalid root OpenAI extension",
    )

    overlay = json.loads(read(".codex-plugin/plugin.json"))
    require(
        all(
            overlay[key] == manifest[key] for key in ("name", "version", "description")
        ),
        "Compatibility manifest mismatch",
    )
    overlay_extensions = overlay.get("extensions", {})
    require(isinstance(overlay_extensions, dict), "Invalid compatibility extensions")
    compatibility_extension = overlay_extensions.get("com.openai")
    require(
        isinstance(compatibility_extension, dict),
        "Invalid compatibility OpenAI extension",
    )
    extension = (
        inline_extension
        if inline_extension is not None
        else compatibility_extension
    )
    require(
        extension.get("onboardingSkill") == "./skills/setup/SKILL.md",
        "Invalid onboarding skill",
    )
    interface = extension.get("interface")
    require(isinstance(interface, dict), "Invalid OpenAI interface")
    short_description = interface.get("shortDescription")
    require(
        isinstance(short_description, str) and len(short_description) <= 30,
        "Description too long",
    )
    require(
        interface.get("category") == "Productivity",
        "Invalid category",
    )
    if inline_extension is not None:
        require(
            compatibility_extension.get("onboardingSkill")
            == inline_extension.get("onboardingSkill"),
            "Compatibility onboarding mismatch",
        )
    require(
        not ((root / ".mcp.json").exists() if files is None else ".mcp.json" in files),
        "Unsupported MCP manifest",
    )
    server = mcp["mcpServers"]["qdrant-memory"]
    compatible = dict(overlay["mcpServers"]["qdrant-memory"])
    env_vars = compatible.pop("env_vars", None)
    require(
        isinstance(env_vars, list)
        and all(isinstance(name, str) for name in env_vars)
        and len(env_vars) == 8
        and set(env_vars)
        == {
            "QDRANT_MEMORY_CODEX_ROOT",
            "QDRANT_MEMORY_CODEX_PROFILE",
            "QDRANT_MEMORY_CODEX_EXECUTABLE",
            "QDRANT_MEMORY_CODEX_PYTHON",
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
        text = read(f"skills/{name}/SKILL.md").replace("\r\n", "\n").replace("\r", "\n")
        require(
            text.startswith("---\n") and f"name: {name}\n" in text,
            "Invalid skill: " + name,
        )
    return manifest


@cache
def _windows_api():
    """Bind only the stdlib builder's missing no-reparse handle operations."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    return kernel


def _windows_normal_name(name):
    if name.startswith("\\\\?\\UNC\\"):
        name = "\\\\" + name[8:]
    elif name.startswith("\\\\?\\"):
        name = name[4:]
    return os.path.normcase(os.path.normpath(name))


def _windows_file_name(handle):
    """Check the opened object, rather than re-resolving its input pathname."""
    import ctypes

    name = ctypes.create_unicode_buffer(32768)
    length = _windows_api().GetFinalPathNameByHandleW(handle, name, len(name), 0)
    if not length:
        raise ctypes.WinError(ctypes.get_last_error())
    require(length < len(name), "Plugin source path is too long")
    return _windows_normal_name(name.value)


def _windows_source_handle(path, directory):
    import ctypes
    from ctypes import wintypes

    kernel = _windows_api()
    flags = 0x200000 | (
        0x2000000 if directory else 0
    )  # OPEN_REPARSE_POINT / BACKUP_SEMANTICS
    access = 0x80 if directory else 0x80000000  # READ_ATTRIBUTES / GENERIC_READ
    # Deny write and delete sharing: checked ancestors cannot be changed while
    # the next full pathname is opened. All directory handles stay held.
    handle = kernel.CreateFileW(str(path), access, 1, None, 3, flags, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes = (wintypes.DWORD * 2)()  # FILE_ATTRIBUTE_TAG_INFO
        if not kernel.GetFileInformationByHandleEx(
            handle, 9, attributes, ctypes.sizeof(attributes)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        require(
            not attributes[0] & 0x400,
            "Plugin source cannot contain symlinks or reparse points",
        )
        require(
            bool(attributes[0] & 0x10) == directory, "Invalid plugin source file type"
        )
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    return handle


def _source_bytes(path):
    """Read the checked file itself, with parents pinned until the read ends."""
    with ExitStack() as resources:
        if os.name == "nt":
            import msvcrt

            kernel = _windows_api()
            for ancestor in reversed(path.parents):
                handle = _windows_source_handle(ancestor, True)
                resources.callback(kernel.CloseHandle, handle)
            expected = path.lstat()
            handle = _windows_source_handle(path, False)
            try:
                descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            except BaseException:
                kernel.CloseHandle(handle)
                raise
        else:
            require(
                bool(getattr(os, "O_NOFOLLOW", 0)) and os.open in os.supports_dir_fd,
                "Secure plugin builds require no-follow directory-relative reads",
            )
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent = os.open(path.anchor, flags)
            resources.callback(os.close, parent)
            for part in path.parts[1:-1]:
                parent = os.open(part, flags, dir_fd=parent)
                resources.callback(os.close, parent)
            expected = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
        resources.callback(os.close, descriptor)
        opened = os.fstat(descriptor)
        require(
            stat.S_ISREG(expected.st_mode),
            "Tracked plugin source must be a regular file",
        )
        require(stat.S_ISREG(opened.st_mode), "Plugin source must be a regular file")
        require(
            opened.st_ino != 0 and os.path.samestat(expected, opened),
            "Plugin source changed during open",
        )
        if os.name == "nt":
            require(
                _windows_file_name(handle) == _windows_normal_name(str(path)),
                "Plugin source resolved outside its checked path",
            )
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            return source.read()


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
        if not path.is_file():
            raise ValueError("Tracked plugin file is missing: " + name)
        relative = str(path.relative_to(PLUGIN)).replace("\\", "/")
        files[relative] = _normalize_text_bytes(relative, _source_bytes(path))
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
                packaged_path = "skills/qdrant-memory/" + str(relative)
                files[packaged_path] = _normalize_text_bytes(
                    packaged_path, archive.extractfile(member).read()
                )
    require(
        "skills/qdrant-memory/SKILL.md" in files, "Pinned upstream skill lacks SKILL.md"
    )
    return files


def build(output, skill_repo):
    """Bundle a precise upstream skill snapshot and content integrity manifest."""
    files = source_files()
    release = json.loads(files["release.json"])
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
    pinned_skills = skill_files(skill_repo, release["skill_commit"])
    repository_skills = {
        name: data
        for name, data in files.items()
        if name.startswith("skills/qdrant-memory/")
    }
    if repository_skills != pinned_skills:
        missing = sorted(pinned_skills.keys() - repository_skills.keys())
        extra = sorted(repository_skills.keys() - pinned_skills.keys())
        changed = sorted(
            name
            for name in repository_skills.keys() & pinned_skills.keys()
            if repository_skills[name] != pinned_skills[name]
        )
        details = []
        for label, paths in (("missing", missing), ("extra", extra), ("changed", changed)):
            if paths:
                details.append(label + "=" + ",".join(paths[:5]))
        raise ValueError(
            "Repository marketplace Skill does not match its pinned snapshot: "
            + "; ".join(details)
        )
    validate(PLUGIN, files)
    files["release.json"] = json.dumps(release, indent=2).encode() + b"\n"
    files["VERIFICATION.md"] = _normalize_text_bytes(
        "VERIFICATION.md", _source_bytes(ROOT / VERIFICATION_PATH)
    )
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
    # Stored entries avoid platform-specific zlib streams. The source package is
    # small enough that cross-platform bit-for-bit archives are more valuable
    # than the modest compression savings.
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("qdrant-memory/" + name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_STORED)
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


def resolve_archive_output(value):
    """Resolve an archive destination within the repository's ignored dist tree."""
    repository = ROOT.resolve(strict=True)
    output_root = repository / "dist"
    if output_root.is_symlink():
        raise ValueError("Plugin archive output directory cannot be a symlink")
    output_root = output_root.resolve()

    output = Path(value).expanduser()
    if not output.is_absolute():
        output = repository / output
    if output.is_symlink():
        raise ValueError("Plugin archive output cannot be a symlink")
    output = output.resolve()
    if output == output_root or not output.is_relative_to(output_root):
        raise ValueError("Plugin archive output must stay inside the repository dist directory")
    if output.exists() and not output.is_file():
        raise ValueError("Plugin archive output must be a regular file")
    return output


def main():
    """Build the pinned plugin archive or validate its offline invariants."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/qdrant-memory-codex-0.1.4.zip"
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
        try:
            output = resolve_archive_output(args.output)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(build(output, args.skill_repo)))


if __name__ == "__main__":
    main()
