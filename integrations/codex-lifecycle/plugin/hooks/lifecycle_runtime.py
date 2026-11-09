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

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_CONTEXT_CHARS = 1800
MAX_CAPTURE_CHARS = 512


class HookError(Exception):
    """A hook-level failure that is surfaced as a systemMessage, not a crash."""


def home(* sub: str) -> Path:
    """Resolve the operator's Codex root/profile paths per the launcher contract."""
    root = os.environ.get("QDRANT_MEMORY_CODEX_ROOT")
    root_path = Path(root).expanduser() if root else Path.home() / ".qdrant-memory" / "codex"
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
    layout = ("Scripts", "qdrant-memory.exe") if platform == "win32" else ("bin", "qdrant-memory")
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
        raise HookError(f"The profile scope at {path} is incomplete; run the setup skill")
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
        raise HookError(f"Runtime {Path(executable).name} {args[0] if args else ''} timed out") from error
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def safe_error(stdout: str, stderr: str) -> str:
    """Pick a single-line diagnostic without leaking payload content."""
    line = stderr.splitlines()[0] if stderr.strip() else stdout.splitlines()[0] if stdout.strip() else "unknown error"
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


def emit(*, additional_context: str | None = None, system_message: str | None = None) -> int:
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
        return 0  # exit 0 with no output means: continue silently
    print(json.dumps(payload))
    return 0


def hook_event_name() -> str:
    """Return the event recorded in the current hook input, for output fidelity."""
    return os.environ.get("CODEX_HOOK_EVENT_NAME") or "SessionStart"
