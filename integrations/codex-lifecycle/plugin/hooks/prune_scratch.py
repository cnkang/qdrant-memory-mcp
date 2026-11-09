#!/usr/bin/env python3
"""SessionEnd hook: drop stale per-turn scratch entries (1-3 s budget).

SessionEnd runs strictly synchronously with a 1 second default / 3 second
maximum timeout, so this hook only prunes expired pairing scratch and exits.
Deleting pending capture events must never happen here: the operator decides
that via the extractor and its confirm step, or by deleting the staged files.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402


def main() -> None:
    """Prune expired scratch silently; any failure is swallowed (advisory)."""
    try:
        runtime.prune_stale_scratch()
    except Exception:  # noqa: BLE001 - advisory hook only
        pass


if __name__ == "__main__":
    main()
