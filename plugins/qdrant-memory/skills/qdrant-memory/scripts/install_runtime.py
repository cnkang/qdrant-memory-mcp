#!/usr/bin/env python3
"""Install the reviewed standalone backend into an explicitly selected private venv.

Print a Hermes advisory and continue. The advisory recommends the native
plugin when it is missing. It notes an installed plugin that is disabled or
not selected as the memory provider, and states that the skill is not
necessary for Hermes when the plugin is enabled and selected. Detection reads
the active Hermes profile (HERMES_HOME, or ~/.hermes) and its config.yaml.
The installer does not run a Hermes command. Other agents can still use the
runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
from pathlib import Path
import subprocess
import sys
import venv
from typing import Sequence

VERSION = "0.6.2"
PLUGIN_ID = "qdrant-memory"
WINDOWS_ACL_UNVERIFIED = "Cannot verify the Windows parent ACL"
WINDOWS_FILE_ACL_UNVERIFIED = "Cannot verify the Windows lock file ACL"


def _require_darwin_allow_acl(path: Path) -> None:
    """Reject a Darwin allow ACL that can override the file's mode bits."""
    if sys.platform != "darwin":
        return
    result = subprocess.run(
        ["/bin/ls", "-lde", str(path)], env={"LC_ALL": "C"},
        check=True, capture_output=True, text=True, timeout=10,
    )
    if any(re.match(r"\s*\d+:.*\ballow\b", line) for line in result.stdout.splitlines()):
        raise ValueError("Choose a private lock path without granting macOS ACL entries")


def _require_private_mkdir() -> None:
    """Reject Windows builds that ignore mkdir's private-directory mode."""
    version = sys.version_info[:3]
    # CPython backported Windows mkdir(0o700) ACL handling to these releases.
    # Older builds must not create an inherited, potentially shared venv first.
    if sys.platform == "win32" and (
        version < (3, 11, 10) or (3, 12) <= version < (3, 12, 4)
    ):
        raise ValueError("Windows setup requires Python 3.11.10+, 3.12.4+, or 3.13+")


_WINDOWS_ACL_SCRIPT = """
$ErrorActionPreference = 'Stop'
$acl = [System.IO.__KIND__]::GetAccessControl($env:__VARIABLE__)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$owners = @($user, 'S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
$owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
if ($owners -notcontains $owner) { exit 3 }
$allowed = $owners + @('S-1-3-0', 'S-1-3-4')
$raw = [System.Security.AccessControl.RawSecurityDescriptor]::new($acl.GetSecurityDescriptorBinaryForm(), 0)
if ($null -eq $raw.DiscretionaryAcl) { exit 3 }
$mask = __ACL_MASK__
$skipInheritOnly = __SKIP_INHERIT_ONLY__
foreach ($entry in $raw.DiscretionaryAcl) {
    if ([int]$entry.AceType -notin @(0, 1)) { exit 3 }
    if ($skipInheritOnly -and (([int]$entry.AceFlags -band 0x08) -ne 0)) { continue }
    $sid = $entry.SecurityIdentifier.Value
    if ([int]$entry.AceType -eq 0 -and
        (([long]$entry.AccessMask -band $mask) -ne 0) -and
        $allowed -notcontains $sid) { exit 3 }
}
exit 0
"""


def _windows_acl_script(*, directory: bool, replacement_only: bool) -> str:
    """Build the PowerShell DACL probe for a lock or one of its ancestors."""
    kind = "Directory" if directory else "File"
    mask = "0x100D0040" if replacement_only else "0x500D0156"
    skip_inherit_only = "$true" if replacement_only else "$false"
    return (
        _WINDOWS_ACL_SCRIPT.replace("__KIND__", kind)
        .replace("__ACL_MASK__", mask)
        .replace("__SKIP_INHERIT_ONLY__", skip_inherit_only)
    )


def _require_windows_acl(
    path: Path, *, directory: bool, label: str, replacement_only: bool = False
) -> None:
    """Reject unsafe Windows DACL grants, optionally limited to path replacement."""
    if os.name != "nt":
        return
    unverified = WINDOWS_ACL_UNVERIFIED if directory else WINDOWS_FILE_ACL_UNVERIFIED
    import ctypes
    from ctypes import wintypes

    # Resolve the Windows binary through the OS, not cwd, PATH or SystemRoot
    # from the caller. The script is constant; the path is environment data.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetWindowsDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetWindowsDirectoryW.restype = wintypes.UINT
    windows = ctypes.create_unicode_buffer(32768)
    length = kernel.GetWindowsDirectoryW(windows, len(windows))
    if not length or length >= len(windows):
        raise ValueError(unverified)
    root = windows.value
    powershell = Path(root) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    variable = "QM_INSTALL_PARENT" if directory else "QM_INSTALL_FILE"
    script = _windows_acl_script(directory=directory, replacement_only=replacement_only)
    script = script.replace("__VARIABLE__", variable)
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
            shell=False, env={"SystemRoot": root, "WINDIR": root, variable: str(path)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(unverified) from exc
    # Includes child deletion and permission changes, not only file writes.
    if result.returncode == 3:
        raise ValueError(f"Choose a {label} without other-account write ACL grants")
    if result.returncode:
        raise ValueError(unverified)


def _require_private_parent(parent: Path) -> None:
    """Reject native ACL grants that can undermine the private venv directory."""
    if sys.platform == "darwin":
        # Darwin allow ACLs can override mode 0700 and propagate to new children.
        # Reject them before mkdir; do not change an operator's existing ACL.
        result = subprocess.run(
            ["/bin/ls", "-lde", str(parent)], env={"LC_ALL": "C"},
            check=True, capture_output=True, text=True, timeout=10,
        )
        if any(re.match(r"\s*\d+:.*\ballow\b", line) for line in result.stdout.splitlines()):
            raise ValueError("Choose a private parent without granting macOS ACL entries")
    elif os.name == "nt":
        _require_windows_acl(parent, directory=True, label="user-controlled parent")


def _require_private_windows_file(path: Path) -> None:
    """Reject a Windows lock file or replaceable ancestor with an unsafe DACL."""
    _require_windows_acl(path, directory=False, label="lock file")
    # The lock and its direct parent get the strict write mask. Effective
    # inherited grants appear on those objects; higher ancestors only need
    # replacement rights checked, so sibling-creation rights do not block use.
    for ancestor in path.parents[1:]:
        _require_windows_acl(
            ancestor, directory=True, label="lock ancestor", replacement_only=True
        )


_COMMENT_LINE_RE = re.compile(r"(^|\s+)#.*$")
_VALUE_OPTIONS = frozenset(
    {
        "-i",
        "--index-url",
        "--pypi-url",
        "--extra-index-url",
        "-f",
        "--find-links",
        "-e",
        "--editable",
        "--trusted-host",
        "--no-binary",
        "--only-binary",
        "--hash",
        "--config-settings",
        "--global-option",
        "--install-option",
        "--progress-bar",
        "--root",
        "--target",
        "--prefix",
        "--src",
        "--upgrade-strategy",
        "--platform",
        "--python-version",
        "--implementation",
        "--abi",
        "--build",
    }
)


def _is_include_option(token: str) -> bool:
    """Return whether one pip option token selects another requirements file."""
    name = token.split("=", 1)[0]
    if name.startswith("--") and len(name) > 2:
        return "--requirement".startswith(name) or "--constraint".startswith(name)
    return name.startswith(("-r", "-c"))


def _logical_lock_lines(text: str):
    """Join backslash continuations the way pip does before option scanning."""
    pending = None
    for line in text.splitlines():
        if not line.endswith("\\") or _COMMENT_LINE_RE.match(line):
            if _COMMENT_LINE_RE.match(line):
                # Keep comments separate; pip does not continue them.
                line = " " + line
            if pending is not None:
                yield pending + line
                pending = None
            else:
                yield line
        else:
            pending = (pending or "") + line.strip("\\")
    if pending is not None:
        yield pending


def _require_self_contained_lock(lock: Path) -> None:
    """Reject a lock that would make pip read another, unvalidated file."""
    try:
        text = lock.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError("Cannot read the requirements lock as UTF-8") from exc
    for line in _logical_lock_lines(text):
        stripped = _COMMENT_LINE_RE.sub("", line).strip()
        if not stripped:
            continue
        try:
            tokens = shlex.split(stripped, comments=False, posix=True)
        except ValueError as exc:
            raise ValueError("Cannot parse the requirements lock") from exc
        skip_value = False
        for token in tokens:
            if skip_value:
                skip_value = False
                continue
            if token in _VALUE_OPTIONS:
                skip_value = True
                continue
            if _is_include_option(token):
                raise ValueError(
                    "--requirements-lock must be self-contained; remove -r/-c includes"
                )


def _release_key(version: str) -> tuple[int, int, int]:
    """Order exact three-part release versions for the compatibility check."""
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def _hermes_home() -> Path | None:
    """Return the active Hermes home: HERMES_HOME when set, else ~/.hermes.

    A relative or unresolvable value returns None. In this case, the default
    home is not used.
    """
    configured = os.environ.get("HERMES_HOME")
    if configured:
        try:
            home = Path(configured).expanduser()
        except (OSError, RuntimeError, ValueError):
            return None
        return home if home.is_absolute() else None
    try:
        return Path.home() / ".hermes"
    except (OSError, RuntimeError, ValueError):
        return None


def hermes_detected() -> bool:
    """Report Hermes on this machine without failing setup."""
    if shutil.which("hermes"):
        return True
    home = _hermes_home()
    if home is None:
        return False
    try:
        return home.is_dir()
    except OSError:
        return False


def _inline_ids(value: str) -> set[str]:
    """IDs from an inline list value such as ``[qdrant-memory, other]``."""
    inner = value.strip().lstrip("[").rstrip("]")
    items: list[str] = []
    buf = ""
    quote = ""
    for char in inner:
        if quote:
            if char == quote:
                quote = ""
            else:
                buf += char
        elif char in "'\"":
            quote = char
        elif char == ",":
            items.append(buf)
            buf = ""
        else:
            buf += char
    items.append(buf)
    return {item.strip() for item in items if item.strip()}


def _flow_disabled_ids(line: str) -> set[str]:
    """IDs from a single-line ``plugins: {disabled: [...]}`` flow mapping."""
    flow = re.fullmatch(r"plugins:[ \t]*\{([^}]*)\}[ \t]*(?:#.*)?", line)
    if not flow:
        return set()
    inner = re.search(
        r"""(?:^|[,\s])['"]?disabled['"]?[ \t]*:[ \t]*\[(.*?)\]""", flow.group(1)
    )
    if not inner:
        return set()
    return _inline_ids("[" + inner.group(1) + "]")


def _disabled_item(line: str) -> str | None:
    """Return the plugin ID from a sequence item line, if any."""
    item = line[1:].split("#", 1)[0].strip().strip("'\"")
    return item or None


def _disabled_key_value(line: str) -> tuple[bool, set[str]]:
    """Return (in_disabled, inline IDs) for one ``plugins`` sub-key line."""
    key, _, value = line.partition(":")
    value = value.split("#", 1)[0].strip()
    in_disabled = key.strip().strip("'\"") == "disabled"
    if not in_disabled or not value.startswith("["):
        return in_disabled, set()
    return in_disabled, _inline_ids(value)


def _disabled_sequence_ids(stripped: str, in_disabled: bool) -> set[str]:
    """Return the plugin ID from a sequence item when disabled items are active."""
    if not in_disabled:
        return set()
    item = _disabled_item(stripped)
    return {item} if item else set()


def _block_lines(lines: Sequence[str]):
    """Yield the stripped line, its indent and the block base indent."""
    base = -1
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1].isspace():
            return
        indent = len(line) - len(line.lstrip())
        if base == -1:
            base = indent
        if indent < base:
            return
        yield stripped, indent, base


def _scan_disabled_block(lines: Sequence[str]) -> set[str]:
    """Scan the block layout of a top-level ``plugins`` mapping."""
    found: set[str] = set()
    in_disabled = False
    for stripped, indent, base in _block_lines(lines):
        if stripped.startswith("-"):
            found.update(_disabled_sequence_ids(stripped, in_disabled))
            continue
        if indent > base:
            continue
        in_disabled, inline = _disabled_key_value(stripped)
        found.update(inline)
    return found


def _scan_disabled_ids(text: str) -> set[str]:
    """Best-effort scan for a top-level ``plugins:`` -> ``disabled:`` items.

    Handles the block layout plus single-line flow mappings such as
    ``plugins: {disabled: [qdrant-memory]}``, tolerating trailing comments,
    blank lines, CRLF endings and indentation variations (sequence items may
    sit at or below the key's indentation). PyYAML stays preferred when
    importable. Only list values are recognized, matching Hermes' own
    parsing. Unparsed shapes (for example flow mappings split across lines)
    yield an empty set. In this case, the plugin keeps its default state:
    enabled.
    """
    found: set[str] = set()
    lines = [raw.rstrip() for raw in text.splitlines()]
    for index, line in enumerate(lines):
        if re.fullmatch(r"plugins:[ \t]*(?:#.*)?", line):
            found.update(_scan_disabled_block(lines[index + 1:]))
            break
        found.update(_flow_disabled_ids(line))
    return found


def _plugin_disabled_in_config(home: Path) -> bool:
    """True when the profile config explicitly disables the plugin.

    A memory backend is active without a ``plugins.enabled`` entry, so only a
    ``plugins.disabled`` entry turns it off. Detection is best effort: prefer
    YAML when available, and scan the block layout otherwise with tolerance
    for comments, blank lines and indentation variations. Unreadable or
    undecodable configs report False (installed and active).
    """
    try:
        text = (home / "config.yaml").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    try:
        import yaml  # optional; the venv under construction may not have it
    except ImportError:
        yaml = None
    if yaml is not None:
        try:
            plugins = (yaml.safe_load(text) or {}).get("plugins")
            if isinstance(plugins, dict) and isinstance(plugins.get("disabled"), list):
                return PLUGIN_ID in {str(item) for item in plugins["disabled"]}
        except Exception:
            pass
    return PLUGIN_ID in _scan_disabled_ids(text)


def _flow_memory_provider(line: str) -> str | None:
    """Provider from a single-line ``memory: {provider: ...}`` flow mapping."""
    flow = re.fullmatch(r"memory:[ \t]*\{([^}]*)\}[ \t]*(?:#.*)?", line)
    if not flow:
        return None
    inner = re.search(
        r"""(?:^|[,\s])['"]?provider['"]?[ \t]*:[ \t]*([^,}\s]+)""", flow.group(1)
    )
    if not inner:
        return None
    return inner.group(1).strip("'\"") or None


def _memory_provider_value(line: str) -> tuple[bool, str | None]:
    """Return (is_provider_key, value) for one ``memory`` sub-key line."""
    key, _, value = line.partition(":")
    if key.strip().strip("'\"") != "provider":
        return False, None
    value = value.split("#", 1)[0].strip().strip("'\"")
    return True, value or None


def _scan_memory_block(lines: Sequence[str]) -> str | None:
    """Scan the block layout of a top-level ``memory`` mapping."""
    for stripped, indent, base in _block_lines(lines):
        if indent > base:
            continue
        is_provider, provider = _memory_provider_value(stripped)
        if is_provider:
            return provider
    return None


def _scan_memory_provider(text: str) -> str | None:
    """Best-effort scan for a top-level ``memory:`` -> ``provider:`` value.

    Handles the block layout plus single-line flow mappings such as
    ``memory: {provider: qdrant-memory}``, with the same tolerance as
    ``_scan_disabled_ids``.
    """
    lines = [raw.rstrip() for raw in text.splitlines()]
    for index, line in enumerate(lines):
        if re.fullmatch(r"memory:[ \t]*(?:#.*)?", line):
            return _scan_memory_block(lines[index + 1:])
        provider = _flow_memory_provider(line)
        if provider is not None:
            return provider
    return None


def _plugin_provider_selected(home: Path) -> bool:
    """True when the profile selects the plugin as its memory provider.

    Detection is best effort and mirrors ``_plugin_disabled_in_config``. An
    unreadable config or a missing ``memory.provider`` value reports False:
    the plugin is then installed but not active.
    """
    try:
        text = (home / "config.yaml").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    try:
        import yaml  # optional; the venv under construction may not have it
    except ImportError:
        yaml = None
    if yaml is not None:
        try:
            memory = (yaml.safe_load(text) or {}).get("memory")
            if isinstance(memory, dict):
                return str(memory.get("provider") or "") == PLUGIN_ID
        except Exception:
            pass
    return _scan_memory_provider(text) == PLUGIN_ID


def hermes_plugin_state() -> str:
    """Return 'absent', 'disabled', 'inactive' or 'enabled' for the active profile."""
    home = _hermes_home()
    if home is None:
        return "absent"
    try:
        if not (home / "plugins" / PLUGIN_ID).is_dir():
            return "absent"
    except OSError:
        return "absent"
    if _plugin_disabled_in_config(home):
        return "disabled"
    if not _plugin_provider_selected(home):
        return "inactive"
    return "enabled"


def hermes_advisory() -> str:
    """Return the Hermes install advisory, or an empty string when none applies."""
    if not hermes_detected():
        return ""
    state = hermes_plugin_state()
    if state == "enabled":
        return (
            "Note: Hermes on this machine already has the qdrant-memory plugin enabled\n"
            "and selected as its memory provider. This skill is not necessary for Hermes:\n"
            "use the native qdrant-memory tools and the \"hermes qdrant-memory\" commands.\n"
            "Other agents can still use the skill, for example Codex, Claude Code,\n"
            "OpenCode or Pi."
        )
    if state == "inactive":
        return (
            "Note: Hermes on this machine has the qdrant-memory plugin installed but\n"
            "not selected as its memory provider. Run \"hermes memory setup\" and\n"
            "select qdrant-memory, or register this skill's MCP server for the profile\n"
            "instead. Other agents can still use the runtime."
        )
    if state == "disabled":
        return (
            "Note: Hermes on this machine has the qdrant-memory plugin installed but\n"
            "disabled. Enable it for the native memory tools (\"hermes plugins enable\n"
            "qdrant-memory\"). Then run \"hermes memory setup\" and select\n"
            "qdrant-memory, or register this skill's MCP server for the profile\n"
            "instead. Other agents can use the runtime either way."
        )
    return (
        "Note: Hermes is present on this machine, but its qdrant-memory plugin is not\n"
        "installed. For Hermes, prefer the plugin: install it from the Plugin Catalog\n"
        "with \"hermes plugins install qdrant-memory\". Other agents can still use this\n"
        "runtime and skill, for example Codex, Claude Code, OpenCode or Pi."
    )


def _validate_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    """Validate version options and return the pip requirement string."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version, re.ASCII):
        parser.error("--version must be an exact three-part release version")
    if args.revision and not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("--revision must be a full lowercase 40-character Git SHA")
    requirement = f"hermes-plugin-qdrant-memory[mcp]=={args.version}"
    if args.revision:
        requirement = "hermes-plugin-qdrant-memory[mcp] @ git+https://github.com/cnkang/hermes-plugin-qdrant-memory.git@" + args.revision
    return requirement


def _resolve_target(parser: argparse.ArgumentParser, selected: Path) -> tuple[Path, Path]:
    """Resolve --venv and require a private, user-owned existing ancestor."""
    if selected.is_symlink():
        parser.error("--venv must not be a symlink")
    target = selected.resolve()
    existing = target
    while not existing.exists():
        existing = existing.parent
    info = existing.stat()
    if os.name != "nt" and (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022):
        parser.error("Choose a venv in a private, user-owned directory")
    return target, existing


def _resolve_lock(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Path | None:
    """Resolve and validate the optional hash-locked requirements file."""
    if args.requirements_lock and args.revision:
        parser.error("--requirements-lock is for release installations, not source revisions")
    if not args.requirements_lock:
        return None
    lock = args.requirements_lock.expanduser().resolve()
    try:
        info = lock.stat()
    except OSError:
        parser.error("--requirements-lock must name a trusted requirements file")
    if not stat.S_ISREG(info.st_mode):
        parser.error("--requirements-lock must name a regular file")
    try:
        _require_private_parent(lock.parent)
        _require_darwin_allow_acl(lock)
        _require_private_windows_file(lock)
        _require_self_contained_lock(lock)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.error(str(exc) or "Cannot verify the requirements-lock permissions")
    if os.name != "nt":
        try:
            parent_info = lock.parent.stat()
        except OSError:
            parser.error("--requirements-lock directory must be accessible")
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != os.getuid()
            or parent_info.st_mode & 0o022
        ):
            parser.error("--requirements-lock must be in a private, user-owned directory")
        for ancestor in lock.parents:
            try:
                ancestor_info = ancestor.stat()
            except OSError:
                parser.error("--requirements-lock directory must be accessible")
            if (
                not stat.S_ISDIR(ancestor_info.st_mode)
                or (
                    ancestor_info.st_mode & 0o022
                    and not ancestor_info.st_mode & 0o1000
                )
                or ancestor_info.st_uid not in {os.getuid(), 0}
            ):
                parser.error(
                    "--requirements-lock must not sit under a directory writable or replaceable by another account"
                )
            try:
                _require_darwin_allow_acl(ancestor)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                parser.error(str(exc) or "Cannot verify the requirements-lock path")
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            parser.error(
                "--requirements-lock must be owned by the current user and not group/world-writable"
            )
    return lock


def _check_shell_safe(parser: argparse.ArgumentParser, target: Path) -> None:
    """Reject venv paths that would make a generated console script unsafe."""
    # pip can generate POSIX console scripts with a shell-wrapper shebang.
    # Keep the interpreter path safe even when subprocess itself uses argv.
    if os.name != "nt" and any(
        char in "\"'`$\\;&|<>(){}[]*?" or ord(char) < 32 or ord(char) == 127
        for char in str(target)
    ):
        parser.error("shell-sensitive characters in --venv path; choose a private path with ordinary names (spaces are supported)")


def _build_env() -> dict[str, str]:
    """Return the minimal environment needed for a public-source install."""
    # Public-source installation needs OS essentials, not agent credentials.
    allowed = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR",
               "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP",
               "TMP", "TMPDIR", "LANG", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR")
    env = {key: value for key in allowed if (value := os.getenv(key)) is not None}
    env["PIP_CONFIG_FILE"] = os.devnull
    return env


def _create_venv(target: Path) -> None:
    """Create the private virtual environment root and its interpreter."""
    _require_private_mkdir()
    # Managed POSIX Python builds can resolve libpython relative to the
    # original executable. Match `python -m venv` rather than copying it.
    # Create the root private: a later chmod would leave a window in which
    # another account could write into the directory pip later imports from.
    previous_umask = os.umask(0o077) if os.name != "nt" else None
    try:
        # Pre-create the root with an explicit private mode so inherited
        # entries are masked before anything runs inside it.
        target.mkdir(mode=0o700, parents=True, exist_ok=False)
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(target)
    finally:
        if previous_umask is not None:
            os.umask(previous_umask)
    if os.name != "nt":
        target.chmod(0o700)


def _pip_selection(target: Path, requirement: str, lock: Path | None) -> tuple[list[str], Path]:
    """Return the pip arguments and working directory for the install."""
    if lock:
        # Use the already resolved and validated path. Re-resolving here could
        # follow a replacement between validation and pip's read.
        return ["--require-hashes", "--only-binary=:all:", "-r", str(lock)], lock.parent
    # Keep the requested version out of the argv; pip reads it from a
    # file this installer writes inside the private venv root.
    requirement_file = target / "runtime-requirements.txt"
    requirement_file.write_text(f"{requirement}\n", encoding="utf-8")
    return ["-r", str(requirement_file)], target.parent


def _install(target: Path, python: Path, requirement: str, lock: Path | None, env: dict[str, str]) -> None:
    """Create the venv when absent and install the selected requirement."""
    if target.exists():
        return
    _create_venv(target)
    selection, pip_cwd = _pip_selection(target, requirement, lock)
    # The executable is the selected venv's Python. Options are fixed;
    # the trusted lock path is one argv element, never shell source.
    # This audit rule treats any CLI-derived argv as command injection.
    subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args
        [str(python), "-I", "-m", "pip", "install", *selection],
        shell=False,
        env=env,
        cwd=pip_cwd,
        check=True,
        stdout=sys.stderr,
    )


def _probe_install(target: Path, python: Path, env: dict[str, str]) -> dict:
    """Import the installed runtime and report its version and source."""
    probe = subprocess.run([str(python), "-I", "-c", "import importlib.metadata as m, json; import qdrant_memory.standalone; from qdrant_memory.mcp_server import create_server; create_server(None); d=m.distribution('hermes-plugin-qdrant-memory'); print(json.dumps({'version': d.version, 'source': json.loads(d.read_text('direct_url.json') or 'null')}))"], env=env, cwd=target, check=True, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
    return json.loads(probe.stdout)


def _verify_install(target: Path, python: Path, console: Path, args: argparse.Namespace, lock: Path | None, env: dict[str, str]) -> dict:
    """Verify the installed version, revision and console entrypoint."""
    installed = _probe_install(target, python, env)
    if lock and installed["version"] != args.version:
        raise ValueError(f"Installed Runtime {installed['version']} does not match requested {args.version}")
    if _release_key(installed["version"]) < _release_key(args.version):
        raise ValueError(f"Installed Runtime {installed['version']} is older than requested {args.version}")
    if args.revision and (installed.get("source") or {}).get("vcs_info", {}).get("commit_id") != args.revision:
        raise ValueError("Installed Runtime source does not match the requested immutable revision")
    subprocess.run([str(console), "--help"], env=env, cwd=target, check=True, stdout=sys.stderr)
    return installed


def main() -> int:
    """Install or verify the runtime selected by the required ``--venv`` CLI path.

    Expand ``~`` and resolve the absolute path. If absent, create a venv and
    install a pinned PyPI release with MCP support, or an explicitly selected
    full Git SHA. Existing environments are verified without upgrading; a
    newer compatible release is accepted.
    On success, print JSON containing ``ok``, absolute ``python`` and ``command``
    paths, requested and installed versions and the optional revision, then return 0.

    Return 1 with a stderr diagnostic for OSError or CalledProcessError during
    creation, installation, or verification, retaining any partial installation.
    Argument parsing, Python 3.11+ and unsafe POSIX path checks raise SystemExit.
    Path expansion/resolution errors and ValueError from venv creation propagate.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", required=True, type=Path, help="new private environment, or an already working installation")
    parser.add_argument("--version", default=VERSION, help="exact Runtime release version (default: %(default)s)")
    parser.add_argument("--requirements-lock", type=Path, help="optional trusted hash-locked requirements for binary-only release installation")
    parser.add_argument("--revision", help="optional full immutable Git SHA for candidate/development installation")
    args = parser.parse_args()
    requirement = _validate_options(parser, args)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11+ is required")
    target, existing = _resolve_target(parser, args.venv.expanduser())
    lock = _resolve_lock(parser, args)
    _check_shell_safe(parser, target)
    try:
        advisory = hermes_advisory()
    except Exception:
        advisory = ""  # The advisory must never fail the install.
    if advisory:
        print(advisory, file=sys.stderr)
    scripts = target / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    console = scripts / ("qdrant-memory.exe" if os.name == "nt" else "qdrant-memory")
    env = _build_env()
    try:
        _require_private_parent(existing)
        # Existing environments are verified, never overwritten or upgraded.
        # A newer compatible release satisfies the check; an older one does not.
        _install(target, python, requirement, lock, env)
        installed = _verify_install(target, python, console, args, lock, env)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        print(f"Runtime installation/verification failed: {exc}. Existing files were retained; choose a new --venv path to retry a partial installation.", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "python": str(python), "command": str(console), "requested_version": args.version, "installed_version": installed["version"], "requested_revision": args.revision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
