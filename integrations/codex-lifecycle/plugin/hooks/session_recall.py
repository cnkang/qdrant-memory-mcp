#!/usr/bin/env python3
"""SessionStart recall hook: surface scoped durable facts as extra context.

Runs on startup, resume, clear, compact and fork. The hook calls the operator's
own Runtime with the current session working directory as a search query and
returns its records through the released ``additionalContext`` contract.
It never scans transcripts and never calls any network service.
"""

from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402


def recall_query(event: dict) -> str:
    """Use the session working directory as the recall query."""
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        from pathlib import PurePath

        return str(PurePath(cwd).name or cwd)
    return ""


def main() -> None:
    """Emit durable records for this scope, or stop silently when none apply."""
    try:
        event = runtime.read_hook_input()
        runtime.load_scope()
        query = recall_query(event)
        if not query:
            runtime.emit(system_message="Qdrant Memory recall skipped: no session cwd")
            return
        status, out, err = runtime.call_runtime("search", "--query", query)
        if status != 0:
            runtime.emit(
                system_message="Qdrant Memory recall unavailable: " + runtime.safe_error(out, err)
            )
            return
        try:
            result = json.loads(out)
        except ValueError as error:
            runtime.emit(system_message=f"Qdrant Memory recall misread Runtime output: {error}")
            return
        memories = result.get("memories") if isinstance(result, dict) else None
        rows = memories if isinstance(memories, list) else []
        if not rows:
            return  # nothing durable to restore; stay silent, not noisy
        lines = []
        for row in rows:
            text = str(row.get("text", "")).strip()
            if text:
                lines.append(f"- {text}")
        if not lines:
            return  # rows exist but carry no text; do not inject an empty header
        context = "Durable Qdrant Memory for this project (review before acting):\n" + "\n".join(lines)
        if len(context) > runtime.DEFAULT_CONTEXT_CHARS:
            context = context[: runtime.DEFAULT_CONTEXT_CHARS - 1] + "…"
        runtime.emit(additional_context=context)
    except runtime.HookError as error:
        runtime.emit(system_message=f"Qdrant Memory recall skipped: {error}")


if __name__ == "__main__":
    main()
