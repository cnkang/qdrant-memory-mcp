#!/usr/bin/env python3
"""Shared runtime access for the optional Qdrant Memory lifecycle hooks.

The existing Python Runtime owns every memory operation. These hooks never
touch Codex transcripts, rollout files, SQLite databases, or any other
non-official mechanism, and they never send data anywhere except the operator's
own configured Runtime profile.

Paths follow the same contract as the Codex plugin launcher:
``QDRANT_MEMORY_CODEX_ROOT``, ``QDRANT_MEMORY_CODEX_PROFILE`` and
``QDRANT_MEMORY_CODEX_EXECUTABLE`` override the defaults
``~/.qdrant-memory/codex/profile`` and
``~/.qdrant-memory/codex/runtime/{bin,Scripts}/qdrant-memory``.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_CONTEXT_CHARS = 1800
MAX_CAPTURE_CHARS = 512

# Capture-stage bounds (aligned with the shared Runtime's extraction-v1
# candidate contract and the DSH adapter): a bounded turn snapshot, never a
# transcript. Limits are byte-exact UTF-8 truncations.
USER_EXCERPT_BYTES = 2048
ASSISTANT_TEXT_BYTES = 8192
MAX_PENDING_EVENTS = 300
SCRATCH_TTL_SECONDS = 48 * 3600

CAPTURE_FORMAT = "qdrant-codex-capture"
CAPTURE_FORMAT_VERSION = 1
PROVENANCE = {
    "capture_source": "codex-hook",
    "plugin": "qdrant-memory-lifecycle",
}


class HookError(Exception):
    """A hook-level failure that is surfaced as a systemMessage, not a crash."""


def home(*sub: str) -> Path:
    """Resolve the operator's Codex root/profile paths per the launcher contract."""
    root = os.environ.get("QDRANT_MEMORY_CODEX_ROOT")
    root_path = (
        Path(root).expanduser() if root else Path.home() / ".qdrant-memory" / "codex"
    )
    target = root_path.joinpath(*sub) if sub else root_path
    return target.expanduser()


def profile_path() -> Path:
    """The private Codex profile directory."""
    configured = os.environ.get("QDRANT_MEMORY_CODEX_PROFILE")
    if configured:
        return Path(configured).expanduser()
    return home("profile")


def runtime_executable() -> Path:
    """The Runtime console script, from the environment or the plugin layout."""
    configured = os.environ.get("QDRANT_MEMORY_CODEX_EXECUTABLE")
    if configured:
        return Path(configured).expanduser()
    platform = sys.platform
    layout = (
        ("Scripts", "qdrant-memory.exe")
        if platform == "win32"
        else ("bin", "qdrant-memory")
    )
    return home("runtime", *layout)


def load_scope() -> tuple[str, str]:
    """Read the fixed profile scope; refuse broken or missing scopes."""
    path = profile_path() / "qdrant-memory.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HookError(f"Cannot read the profile scope at {path}: {error}") from error
    scope = config.get("scope") or {}
    user, agent = scope.get("user_id"), scope.get("agent_id")
    if not isinstance(user, str) or not isinstance(agent, str) or not user or not agent:
        raise HookError(
            f"The profile scope at {path} is incomplete; run the setup skill"
        )
    return user, agent


def call_runtime(*args: str, timeout: float = 20.0) -> tuple[int, str, str]:
    """Invoke the Runtime CLI with direct argv (never a shell)."""
    executable = runtime_executable()
    command = [
        str(executable),
        "--home",
        str(profile_path()),
        *args,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except OSError as error:
        raise HookError(f"Runtime {executable} is not usable: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise HookError(
            f"Runtime {Path(executable).name} {args[0] if args else ''} timed out"
        ) from error
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def safe_error(stdout: str, stderr: str) -> str:
    """Pick a single-line diagnostic without leaking payload content."""
    line = (
        stderr.splitlines()[0]
        if stderr.strip()
        else stdout.splitlines()[0]
        if stdout.strip()
        else "unknown error"
    )
    return line[:220]


def read_hook_input() -> dict:
    """Read one JSON hook event from stdin; tolerate empty input."""
    try:
        raw = sys.stdin.read()
    except OSError as error:  # pragma: no cover - defensive
        raise HookError(f"Cannot read hook input: {error}") from error
    if not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except ValueError as error:
        raise HookError(f"Invalid hook input JSON: {error}") from error
    if not isinstance(event, dict):
        raise HookError("Hook input must be a JSON object")
    return event


def emit(
    *, additional_context: str | None = None, system_message: str | None = None
) -> int:
    """Print the released hooks output contract for context-bearing events."""
    payload: dict = {}
    if system_message:
        payload["systemMessage"] = system_message
    if additional_context is not None:
        payload["hookSpecificOutput"] = {
            "hookEventName": hook_event_name(),
            "additionalContext": additional_context,
        }
    elif system_message is None:
        return 0  # no output means: continue silently
    print(json.dumps(payload))
    return 0


def hook_event_name() -> str:
    """Return the event recorded in the current hook input, for output fidelity."""
    return os.environ.get("CODEX_HOOK_EVENT_NAME") or "SessionStart"


def truncate_utf8(text: str, limit: int) -> tuple[str, bool]:
    """Return text truncated to at most ``limit`` UTF-8 bytes (never mid-codepoint)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False
    clipped = encoded[:limit]
    while clipped:
        try:
            return clipped.decode("utf-8"), True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "", True


def events_root() -> Path:
    """Durable capture staging under the profile (survives plugin uninstall)."""
    return profile_path() / "events" / "codex"


def scratch_root() -> Path:
    """Per-turn user-text scratch, PLUGIN_DATA when Codex provides it."""
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        return Path(plugin_data).expanduser() / "turn_inputs"
    return events_root() / "scratch"


def pending_dir() -> Path:
    return events_root() / "pending"


def extracted_dir() -> Path:
    return events_root() / "extracted"


def discarded_dir() -> Path:
    return events_root() / "discarded"


def event_id_for(session_id: str, turn_id: str) -> str:
    """Deterministic, opaque event ID (DSH parity: session/turn-derived sha256)."""
    digest = hashlib.sha256(
        f"{CAPTURE_FORMAT}:{CAPTURE_FORMAT_VERSION}:{session_id}:{turn_id}".encode(
            "utf-8"
        )
    ).hexdigest()
    return f"codex-auto-{digest}"


def write_json_private(path: Path, payload) -> None:
    """Create private parent directories and write the file (0600 on POSIX).

    Windows ignores the POSIX mode bits; the profile directory's own private
    placement is the boundary there (documented in the lifecycle README).
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        if os.name != "nt":
            os.fchmod(handle.fileno(), 0o600)
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_json(path: Path):
    """Read one staged JSON document; None if unreadable or malformed."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def now_utc() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat(
        timespec="milliseconds"
    )


def pending_count() -> int:
    try:
        return sum(
            1 for p in pending_dir().glob("*.json") if not p.name.endswith(".tmp")
        )
    except OSError:
        return 0


def count_overflow_marker() -> int:
    path = events_root() / "dropped.d"
    try:
        return int(path.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def mark_overflow(count: int = 1) -> None:
    path = events_root() / "dropped.d"
    try:
        current = count_overflow_marker()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(str(current + count), encoding="utf-8")
    except OSError:
        pass


def prune_stale_scratch(
    ttl_seconds: int = SCRATCH_TTL_SECONDS, now: float | None = None
) -> int:
    """Best-effort cleanup of unpaired per-turn scratch entries."""
    now = time.time() if now is None else now
    removed = 0
    root = scratch_root()
    try:
        for entry in root.glob("*.json"):
            try:
                if now - entry.stat().st_mtime > ttl_seconds:
                    entry.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed


def scratch_path_for(session_id: str, turn_id: str) -> Path:
    digest = hashlib.sha256(f"{session_id}\x1f{turn_id}".encode("utf-8")).hexdigest()
    return scratch_root() / f"{digest}.json"
