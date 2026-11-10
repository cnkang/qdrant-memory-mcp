#!/usr/bin/env python3
"""Stop hook: pair the completed turn into one bounded, local pending event.

Behavior contract (auto-capture preview; switched off by removing this entry
from ``hooks.json``):

* Runs ``async`` so turn latency stays zero. Output only surfaces as a
  systemMessage, never in the model context.
* Pairs ``last_assistant_message`` with the turn's locally staged user text
  from the scratch store (session+turn pairing, with a session-level fallback
  for clients that omit ``turn_id``). If either side is missing or empty, the
  turn is simply not captured.
* Writes at most one bounded JSON snapshot per turn under the operator's
  profile ``events/codex/pending/`` (mode 0600; byte-capped 2 KiB user excerpt
  and 8 KiB assistant text). Deterministic ``event_id`` per session+turn, so
  a repeated run for the same turn overwrites instead of duplicating —
  including at ring capacity, where only newly added events count.
* The capacity check, the write and the overflow marker update run under one
  profile-local lock, so concurrent Stop hooks cannot exceed the 300-event
  cap or lose overflow counts.
* Never calls the Runtime, never invokes a model, never reads Codex
  transcripts or rollout files, never writes to the Qdrant collection.
* Best effort by design: a local failure exits silently (or with one
  systemMessage line that contains no turn content).

Deleting pending entries (or the whole ``events/codex`` directory) before
extraction is the operator's abort for captured content; extraction is a
separate, explicit step.
"""

from __future__ import annotations

import hashlib
import sys

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402


def _paired_scratch(session_id: str, turn_id, has_turn: bool):
    """Return the pairing scratch for this turn, falling back to the session."""
    scratch = None
    if has_turn:
        scratch = runtime.read_json(runtime.scratch_path_for(session_id, turn_id))
    if not isinstance(scratch, dict):
        scratch = runtime.read_json(runtime.scratch_session_path(session_id))
    return scratch if isinstance(scratch, dict) else None


def _turn_key(turn_id, has_turn: bool, assistant_raw: str) -> str:
    """Deterministic turn key: session turn id, else a reply-content digest."""
    if has_turn:
        return turn_id
    digest = hashlib.sha256(assistant_raw.encode("utf-8")).hexdigest()[:16]
    return f"reply:{digest}"


def _capture_payload(
    session_id: str,
    turn_key: str,
    scratch: dict,
    assistant_text: str,
    assistant_truncated: bool,
) -> dict:
    """Build the bounded pending-event payload for one completed turn."""
    return {
        "format": runtime.CAPTURE_FORMAT,
        "version": runtime.CAPTURE_FORMAT_VERSION,
        "event_id": runtime.event_id_for(session_id, turn_key),
        "session_id": session_id,
        "turn_id": turn_key,
        "stored_utc": runtime.now_utc(),
        "cwd": scratch.get("cwd") if isinstance(scratch.get("cwd"), str) else "",
        "user_text": {
            "excerpt": scratch.get("user_excerpt"),
            "truncated": bool(scratch.get("user_truncated")),
        },
        "assistant_text": {
            "text": assistant_text,
            "truncated": assistant_truncated,
        },
        "status": "pending",
        "provenance": {
            **runtime.PROVENANCE,
            "plugin_version": runtime.PLUGIN_VERSION,
        },
    }


def _consume_scratch(session_id: str, turn_id, has_turn: bool) -> None:
    """Remove the pairing scratch once its turn is captured."""
    paths = {runtime.scratch_session_path(session_id)}
    if has_turn:
        paths.add(runtime.scratch_path_for(session_id, turn_id))
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


def capture(event: dict) -> None:
    """Store one pending event for this completed turn; never fail the turn."""
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    if event.get("stop_hook_active") is True:
        return  # continuation turn of a decided Stop; do not chain captures
    turn_id = event.get("turn_id")
    has_turn = isinstance(turn_id, str) and bool(turn_id)
    assistant_raw = event.get("last_assistant_message")
    if not isinstance(assistant_raw, str) or not assistant_raw.strip():
        return
    scratch = _paired_scratch(session_id, turn_id, has_turn)
    if scratch is None:
        return
    user_excerpt = scratch.get("user_excerpt")
    if not isinstance(user_excerpt, str) or not user_excerpt.strip():
        return
    assistant_text, assistant_truncated = runtime.truncate_utf8(
        assistant_raw.strip(), runtime.ASSISTANT_TEXT_BYTES
    )
    turn_key = _turn_key(turn_id, has_turn, assistant_raw)
    payload = _capture_payload(
        session_id, turn_key, scratch, assistant_text, assistant_truncated
    )
    if runtime.write_pending_event(payload) == "full":
        runtime.emit(
            system_message=(
                "Qdrant Memory capture paused: pending buffer is full; "
                "run the extractor (extract_pending.py) to free space."
            )
        )
        return
    _consume_scratch(session_id, turn_id, has_turn)



def main() -> None:
    """Read the Stop event, capture best-effort, then prune stale scratch."""
    try:
        event = runtime.read_hook_input()
        capture(event)
        runtime.prune_stale_scratch()
    except Exception:  # noqa: BLE001 - hooks must never break the turn
        # Content-free diagnostic: local storage or input failed, no turn
        # content was read into the failure, and the turn itself continues.
        runtime.emit(
            system_message=(
                "Qdrant Memory auto-capture hit a local error and skipped "
                "this turn; no turn content was stored."
            )
        )


if __name__ == "__main__":
    main()
