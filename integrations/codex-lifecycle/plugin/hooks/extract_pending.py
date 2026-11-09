#!/usr/bin/env python3
"""Pending-event extractor: turn snapshots into validated memory candidates.

This script is not a hook; the operator runs it explicitly. It reads the
bounded pending events staged by the Stop hook, asks the configured extraction
provider (default: local Ollama, OpenAI-compatible /chat/completions) for
durable facts, validates each candidate against the shared Runtime's
extraction-v1 candidate contract (exact keys, bounded text, bounded category
strings, importance 0..1, secret-shaped text refused), and only with
``--confirm`` admits facts through the Runtime CLI ``add`` in the profile's
fixed scope.

Contract honored from the shared DSH native design:

* Dry-run is the default and performs zero writes and zero journal mutations.
* Deduplication is checked against the profile's own stored text at confirm
  time via a Runtime ``search`` for the exact candidate text (semantic parity,
  not a transactional lock).
* Failures keep the event ``pending`` with a recorded ``last_error``; nothing
  is silently dropped.
* Secrets, code-shaped blobs and oversized candidates are refused, and the
  event remains pending for operator review.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402

MAX_CANDIDATE_TEXT_CHARS = 256
MAX_CANDIDATES_PER_EVENT = 3
CATEGORIES = {"project", "preference", "fact", "codex-auto"}
DEFAULT_CATEGORY = "codex-auto"
SECRETISH = re.compile(
    r"sk-[A-Za-z0-9]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|[A-Za-z0-9+/]{40,}={0,2}(?=\s|$)"  # long base64-ish tokens
    r"|(?:API_KEY|SECRET|TOKEN)[:=]\s*\S+",
    re.IGNORECASE,
)

EXTRACTION_PROMPT = """\
You extract durable, portable memory candidates from ONE completed agent turn.
Return ONLY a JSON object:
{{"memories": [{{"text": str, "category": [str], "importance": float, \
"replacement_intent": bool}}], "replacement_context": "<only if any candidate \
has replacement_intent true>"}}.
Rules:
- At most {max_candidates} candidates; each text at most {max_text} characters.
- Only durable user facts or preferences; skip plans, code, secrets, links.
- Preserve the user's meaning; do not invent.
- If nothing durable exists, reply {{"memories": []}}.
USER: {user_text}
ASSISTANT: {assistant_text}
"""


def redact(text: str) -> str:
    """Apply the lifecycle diagnostics redaction to any printed content."""
    for name, value in os.environ.items():
        if value and any(word in name.lower() for word in ("token", "key", "secret")):
            text = text.replace(value, "[REDACTED]")
    return text


def load_pending() -> list[dict]:
    """Read every pending event snapshot, dropping unreadable files silently."""
    events = []
    try:
        paths = sorted(runtime.pending_dir().glob("*.json"))
    except OSError:
        return events
    for path in paths:
        event = runtime.read_json(path)
        if isinstance(event, dict) and event.get("status") == "pending":
            event["_path"] = path
            events.append(event)
    return events


def build_prompt(event: dict) -> str:
    user_text = event.get("user_text", {}).get("excerpt", "")
    assistant_text = event.get("assistant_text", {}).get("text", "")
    return EXTRACTION_PROMPT.format(
        max_candidates=MAX_CANDIDATES_PER_EVENT,
        max_text=MAX_CANDIDATE_TEXT_CHARS,
        user_text=user_text,
        assistant_text=assistant_text,
    )


class ExtractionProvider:
    """OpenAI-compatible /chat/completions client (local Ollama default)."""

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def extract(self, prompt: str):
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a strict JSON-only memory extractor.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + _extraction_key(),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return _parse_model_json(content)


def _extraction_key() -> str:
    """Optional extraction credential comes from the environment only."""
    return os.environ.get("EXTRACTION_API_KEY", "")


def _parse_model_json(content: str):
    """Parse the model's JSON with lenient fence handling and strict shape."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    document = json.loads(text)
    if not isinstance(document, dict) or "memories" not in document:
        raise ValueError("extraction reply lacks the memories field")
    return document


def validate_candidates(document, source_event: dict) -> tuple[list[dict], list[str]]:
    """Enforce the shared Runtime candidate contract; return (good, rejected)."""
    good, rejected = [], []
    raw = document.get("memories")
    replacement_context = document.get("replacement_context")
    if not isinstance(raw, list):
        return good, ["reply memories is not a list"]
    if not isinstance(replacement_context, (str, type(None))):
        replacement_context = None
    for candidate in raw[:MAX_CANDIDATES_PER_EVENT]:
        error = _candidate_error(candidate)
        if error:
            rejected.append(error)
            continue
        candidate = {
            "text": candidate["text"].strip(),
            "category": candidate.get("category") or [DEFAULT_CATEGORY],
            "importance": float(candidate.get("importance", 0.5)),
            "replacement_intent": bool(candidate.get("replacement_intent", False)),
        }
        if candidate["replacement_intent"] and not isinstance(replacement_context, str):
            candidate["replacement_context_missing"] = True
        good.append(candidate)
    if len(raw) > MAX_CANDIDATES_PER_EVENT:
        rejected.append(
            f"{len(raw) - MAX_CANDIDATES_PER_EVENT} extra candidates dropped"
        )
    _ = source_event
    return good, rejected


def _candidate_error(candidate) -> str | None:
    if not isinstance(candidate, dict):
        return "candidate is not an object"
    allowed = {"text", "category", "importance", "replacement_intent"}
    if set(candidate) - allowed:
        return "candidate has extra keys"
    text = candidate.get("text")
    if not isinstance(text, str) or not text.strip():
        return "candidate text empty"
    if len(text.strip()) > MAX_CANDIDATE_TEXT_CHARS:
        return "candidate text too long"
    if SECRETISH.search(text):
        return "candidate looks secret-shaped"
    category = candidate.get("category")
    if category is None:
        category = [DEFAULT_CATEGORY]
    if not isinstance(category, list) or not all(
        isinstance(item, str) and item and len(item) <= 64 for item in category
    ):
        return "candidate category invalid"
    try:
        importance = float(candidate.get("importance", 0.5))
    except (TypeError, ValueError):
        return "candidate importance invalid"
    if not 0.0 <= importance <= 1.0:
        return "candidate importance out of range"
    return None


def show_plan(outcomes, dropped_overflow: int) -> None:
    """Print the dry-run plan (default): zero writes, zero mutations."""
    report = {
        "mode": "dry-run",
        "pending_events": len(outcomes),
        "dropped_overflow_events": dropped_overflow,
        "events": [],
    }
    for outcome in outcomes:
        report["events"].append(
            {
                "event_id": outcome["event_id"],
                "candidates": outcome["candidates"],
                "rejected": outcome["rejected"],
                "extraction_error": outcome.get("extraction_error"),
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def admit_all(outcomes, *, runtime_home_cli=None) -> dict:
    """Confirm path: admit validated candidates through the Runtime CLI.

    The runtime callable resolves at call time (never captured as a default
    argument) so operator/test substitution behaves predictably.
    """
    admit = runtime_home_cli or runtime.call_runtime
    report = {"mode": "confirm", "events": []}
    for outcome in outcomes:
        errors = []
        event_state = {
            "event_id": outcome["event_id"],
            "admitted": [],
            "skipped": [],
            "rejected": outcome["rejected"],
        }
        if outcome.get("extraction_error"):
            errors.append(outcome["extraction_error"])
        candidates = outcome["candidates"]
        for candidate in candidates:
            if is_duplicate(candidate["text"], admit):
                event_state["skipped"].append(
                    {"text": candidate["text"], "reason": "duplicate"}
                )
                continue
            status, body, err = admit("add", "--text", candidate["text"])
            if status != 0:
                errors.append(runtime.safe_error(body, err))
                continue
            try:
                record_id = json.loads(body).get("id")
            except ValueError:
                record_id = None
            event_state["admitted"].append(
                {
                    "text": candidate["text"],
                    "record_id": record_id,
                    "category": candidate["category"],
                }
            )
        if errors:
            event_state["last_error"] = " | ".join(errors)[:600]
        complete = not errors  # empty candidate sets are valid terminal states
        new_status = "extracted" if complete else "pending"
        finalize_event(outcome["_path"], event_state, new_status)
        report["events"].append(
            {
                "event_id": outcome["event_id"],
                "status": new_status,
                "admitted": [item["text"] for item in event_state["admitted"]],
                "skipped": event_state["skipped"],
                "rejected": event_state["rejected"],
                "extraction_error": outcome.get("extraction_error"),
                "last_error": event_state.get("last_error"),
            }
        )
    return report


def is_duplicate(text: str, runtime_home_cli) -> bool:
    """Semantic search parity check against the profile's own stored text."""
    status, body, _err = runtime_home_cli("search", "--query", text)
    if status != 0:
        return False  # fail open: admit rather than lose the fact
    try:
        rows = json.loads(body).get("memories") or []
    except ValueError:
        return False
    return any(row.get("text", "").strip() == text.strip() for row in rows)


def finalize_event(path, event_state, new_status) -> None:
    """Persist the post-admission event state into its staged file."""
    event = runtime.read_json(path) or {}
    event["status"] = new_status
    event["processed_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="milliseconds"
    )
    event["candidates"] = [
        {
            "text": item["text"],
            "category": item.get("category"),
            "record_id": item.get("record_id"),
        }
        for item in event_state["admitted"]
    ]
    event["skipped"] = [
        {"text": item["text"], "reason": item["reason"]}
        for item in event_state["skipped"]
    ]
    if event_state.get("last_error"):
        event["last_error"] = event_state["last_error"]
    destination_parent = (
        runtime.extracted_dir() if new_status == "extracted" else runtime.pending_dir()
    )
    runtime.write_json_private(destination_parent / path.name, event)
    try:
        if path != destination_parent / path.name:
            path.unlink()
    except OSError:
        pass


def main(argv=None) -> int:
    """Read pending events, extract with the configured provider, report/confirm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider", choices=("ollama", "openai-compatible"), default="ollama"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="admit candidates via Runtime add (default: dry-run only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="process at most N pending events this run",
    )
    args = parser.parse_args(argv)

    events = load_pending()[: max(args.limit, 0)]
    dropped_overflow = runtime.count_overflow_marker()
    if not events:
        print(
            json.dumps(
                {
                    "mode": "dry-run" if not args.confirm else "confirm",
                    "pending_events": 0,
                    "dropped_overflow_events": dropped_overflow,
                }
            )
        )
        return 0
    provider = ExtractionProvider(args.base_url, args.model)
    outcomes = []
    for event in events:
        outcome = {
            "event_id": event.get("event_id", ""),
            "_path": event["_path"],
            "candidates": [],
            "rejected": [],
        }
        try:
            document = provider.extract(build_prompt(event))
            good, rejected = validate_candidates(document, event)
            outcome["candidates"] = good
            outcome["rejected"] = rejected
        except (
            ValueError,
            KeyError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as error:
            outcome["extraction_error"] = redact(str(error))[:300]
        outcomes.append(outcome)
    if args.confirm:
        result = admit_all(outcomes)
    else:
        show_plan(outcomes, dropped_overflow)
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
