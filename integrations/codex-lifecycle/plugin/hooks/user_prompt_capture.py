#!/usr/bin/env python3
"""UserPromptSubmit hook: record the turn input; honor explicit remember: lines.

Two independent behaviors, one hook:

1. Pairing record (auto-capture prerequisite, replaceable): the direct user
   text for this turn is staged locally so a later Stop hook can pair it
   with the assistant's reply — keyed by session+turn when ``turn_id`` is
   present, by session alone when the client omits it. This is a bounded
   local scratch entry; it never contacts the Runtime, never builds a memory,
   and it does not change what the Codex model sends or receives. Set
   ``QDRANT_MEMORY_CODEX_AUTO_CAPTURE=0`` to stop this scratch write;
   removing only the Stop hook still stages prompts until the TTL prune.
   The scratch entry's privacy scope equals the remember: switch below: local
   disk only, expiring after ``SCRATCH_TTL_SECONDS`` (48 h by default).

2. Explicit directive (unchanged behavior): a first line starting with
   ``remember:`` or ``remember：`` (case-insensitive) saves the exact
   remainder, including trailing whitespace, via the Runtime CLI. No other
   text is extracted, guessed, or summarized, and there is no model call here.
"""

from __future__ import annotations

import os
import re
import sys

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402

DIRECTIVE = re.compile(r"^\s*remember\s*[:：](.*)$", re.IGNORECASE)
STAGE_FAILURE = (
    "Qdrant Memory could not stage this turn's input locally; "
    "this turn will not be auto-captured."
)


def stage_turn_input(event: dict, prompt: str) -> str | None:
    """Persist the bounded, per-turn user text scratch for Stop-time pairing.

    Codex documents ``turn_id`` for the Stop event but may omit it on
    ``UserPromptSubmit``. When the prompt event carries a ``turn_id`` the
    scratch is keyed by session+turn (exact pairing); otherwise it is keyed by
    session alone and the next Stop hook in that session pairs it. Return a
    content-free diagnostic when the scratch write fails; otherwise return
    None.
    """
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    turn_id = event.get("turn_id")
    has_turn = isinstance(turn_id, str) and bool(turn_id)
    excerpt, truncated = runtime.truncate_utf8(prompt, runtime.USER_EXCERPT_BYTES)
    record = {
        "session_id": session_id,
        "cwd": event.get("cwd") if isinstance(event.get("cwd"), str) else "",
        "user_excerpt": excerpt,
        "user_truncated": truncated,
        "stored_utc": runtime.now_utc(),
    }
    if has_turn:
        record["turn_id"] = turn_id
        record["pairing"] = "turn"
        path = runtime.scratch_path_for(session_id, turn_id)
    else:
        record["pairing"] = "session"
        path = runtime.scratch_session_path(session_id)
    try:
        runtime.write_json_private(path, record)
    except OSError:
        return STAGE_FAILURE
    return None


def _emit_status(message: str, stage_diagnostic: str | None = None) -> int:
    """Emit one hook response, including any best-effort staging failure."""
    if stage_diagnostic:
        message = f"{stage_diagnostic} {message}" if message else stage_diagnostic
    return runtime.emit(system_message=message)


def main() -> int:
    """Stage the turn input, then honor an explicit remember: line if present."""
    stage_diagnostic = None
    try:
        event = runtime.read_hook_input()
        prompt = event.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return 0
        # 1. Pairing record: local scratch, best effort, never fatal.
        if os.environ.get("QDRANT_MEMORY_CODEX_AUTO_CAPTURE", "1") != "0":
            stage_diagnostic = stage_turn_input(event, prompt)
        # 2. Explicit directive (existing contract).
        line = prompt.splitlines()[0]
        match = DIRECTIVE.match(line)
        if not match:
            return _emit_status("", stage_diagnostic) if stage_diagnostic else 0
        text = match.group(1)
        if not text.strip():
            return _emit_status("", stage_diagnostic) if stage_diagnostic else 0
        if len(text) > runtime.MAX_CAPTURE_CHARS:
            return _emit_status(
                "Qdrant Memory did not save: the remember: line exceeds "
                f"{runtime.MAX_CAPTURE_CHARS} characters; shorten and retry.",
                stage_diagnostic,
            )
        runtime.load_scope()  # fail closed for complete profiles only
        status, out, err = runtime.call_runtime("add", "--text", text)
        if status != 0:
            return _emit_status(
                "Qdrant Memory did not save: " + runtime.safe_error(out, err),
                stage_diagnostic,
            )
        return _emit_status("Qdrant Memory saved one explicit fact.", stage_diagnostic)
    except runtime.HookError as error:
        return _emit_status(
            f"Qdrant Memory did not save: {error}", stage_diagnostic
        )


if __name__ == "__main__":
    main()
