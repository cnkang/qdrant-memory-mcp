#!/usr/bin/env python3
"""UserPromptSubmit hook: capture only what the user explicitly asks to remember.

The user writes a line starting with ``remember:`` (case-insensitive). The exact
remaining text of that line is saved verbatim to the operator's own Runtime
profile. Nothing is extracted, summarized, or guessed: there is no model call
in this hook and no other content is captured. Any other prompt exits silently.
"""

from __future__ import annotations

import json
import re
import sys

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402

DIRECTIVE = re.compile(r"^\s*remember\s*[:：]\s*(\S.*\S|\S)\s*$", re.IGNORECASE)


def main() -> None:
    """Save the explicit directive if present; otherwise stay silent."""
    try:
        event = runtime.read_hook_input()
        prompt = event.get("prompt")
        if not isinstance(prompt, str):
            return
        line = prompt.splitlines()[0] if prompt.strip() else ""
        match = DIRECTIVE.match(line)
        if not match:
            return
        text = match.group(1)
        if len(text) > runtime.MAX_CAPTURE_CHARS:
            runtime.emit(
                system_message=(
                    "Qdrant Memory did not save: the remember: line exceeds "
                    f"{runtime.MAX_CAPTURE_CHARS} characters; shorten and retry."
                )
            )
            return
        runtime.load_scope()  # fail closed for complete profiles only
        status, out, err = runtime.call_runtime("add", "--text", text)
        if status != 0:
            runtime.emit(
                system_message="Qdrant Memory did not save: " + runtime.safe_error(out, err)
            )
            return
        try:
            saved = json.loads(out).get("id")
        except ValueError:
            saved = None
        _ = saved  # the Runtime IDs are never needed by the client here
        runtime.emit(system_message="Qdrant Memory saved one explicit fact.")
    except runtime.HookError as error:
        runtime.emit(system_message=f"Qdrant Memory did not save: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
