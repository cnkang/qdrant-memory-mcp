#!/usr/bin/env python3
"""Stop hook: pair the completed turn into one bounded, local pending event.

Behavior contract (auto-capture preview; switched off by removing this entry
from ``hooks.json``):

* Runs ``async`` so turn latency stays zero. Output only surfaces as a
  systemMessage, never in the model context.
* Pairs ``last_assistant_message`` with the turn's locally staged user text
  from the scratch store. If either side is missing or empty, the turn is
  simply not captured.
* Writes at most one bounded JSON snapshot per turn under the operator's
  profile ``events/codex/pending/`` (mode 0600; byte-capped 2 KiB user excerpt
  and 8 KiB assistant text). Deterministic ``event_id`` per session+turn, so
  a repeated run for the same turn overwrites instead of duplicating.
* Never calls the Runtime, never invokes a model, never reads Codex
  transcripts or rollout files, never writes to the Qdrant collection.
* Best effort by design: a local failure exits silently (or with one
  systemMessage line that contains no turn content).

Deleting pending entries (or the whole ``events/codex`` directory) before
extraction is the operator's abort for captured content; extraction is a
separate, explicit step.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402


def capture(event: dict) -> int:
    """Store one pending event for this completed turn; return the exit code."""
    session_id = event.get("session_id")
    turn_id = event.get("turn_id")
    if (
        not isinstance(session_id, str)
        or not isinstance(turn_id, str)
        or not session_id
        or not turn_id
    ):
        return 0
    if event.get("stop_hook_active") is True:
        return 0  # continuation turn of a decided Stop; do not chain captures
    assistant_raw = event.get("last_assistant_message")
    if not isinstance(assistant_raw, str) or not assistant_raw.strip():
        return 0
    scratch = runtime.read_json(runtime.scratch_path_for(session_id, turn_id))
    if not isinstance(scratch, dict):
        # Interrupted or tool-only turn: nothing paired, nothing captured.
        return 0
    user_excerpt = scratch.get("user_excerpt")
    if not isinstance(user_excerpt, str) or not user_excerpt.strip():
        return 0
    if runtime.pending_count() >= runtime.MAX_PENDING_EVENTS:
        runtime.mark_overflow()
        return runtime.emit(
            system_message=(
                "Qdrant Memory capture paused: pending buffer is full; "
                "run the extractor (extract_pending.py) to free space."
            )
        )
    assistant_text, assistant_truncated = runtime.truncate_utf8(
        assistant_raw.strip(), runtime.ASSISTANT_TEXT_BYTES
    )
    payload = {
        "format": runtime.CAPTURE_FORMAT,
        "version": runtime.CAPTURE_FORMAT_VERSION,
        "event_id": runtime.event_id_for(session_id, turn_id),
        "session_id": session_id,
        "turn_id": turn_id,
        "stored_utc": runtime.now_utc(),
        "cwd": scratch.get("cwd") if isinstance(scratch.get("cwd"), str) else "",
        "user_text": {
            "excerpt": user_excerpt,
            "truncated": bool(scratch.get("user_truncated")),
        },
        "assistant_text": {
            "text": assistant_text,
            "truncated": assistant_truncated,
        },
        "status": "pending",
        "provenance": {**runtime.PROVENANCE, "plugin_version": "0.2.0"},
    }
    runtime.write_json_private(
        runtime.pending_dir() / (payload["event_id"] + ".json"), payload
    )
    try:
        runtime.scratch_path_for(session_id, turn_id).unlink()
    except OSError:
        pass
    return 0


def main() -> int:
    """Read the Stop event, capture best-effort, then prune stale scratch."""
    try:
        event = runtime.read_hook_input()
        exit_code = capture(event)
        runtime.prune_stale_scratch()
        return exit_code
    except Exception:  # noqa: BLE001 - hooks must never break the turn
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
