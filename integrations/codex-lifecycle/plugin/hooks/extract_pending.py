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
  It never sends staged turn text to a non-loopback provider; remote providers
  require the explicit ``--confirm`` invocation as consent.
* Non-loopback endpoints must use HTTPS; plaintext HTTP is refused before any
  staged text or credential leaves the machine.
* Duplicate checking and admission run under one profile-local lock, so
  concurrent extractor runs cannot both miss and double-admit one candidate.
* Replacement candidates locate the outdated memory (search before the add so
  the new record cannot match itself), delete it after a successful add, and
  persist the whole decision in the event's durable receipt.
* Runtime or storage failures keep the event ``pending`` with a recorded
  ``last_error`` (plus a retry counter) and never abort the batch; successful
  retries clear both. Previously admitted receipts and their record IDs are
  preserved across retries.
* A snapshot that changed on disk between loading and admission is left
  pending untouched (the newer content wins; nothing stale is admitted).
* Secrets, code-shaped blobs and oversized candidates are refused, refusal
  reasons are persisted in the event file, and unreadable pending files are
  quarantined (renamed ``*.corrupt``) instead of silently consuming ring
  capacity.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.client
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402

MAX_CANDIDATE_TEXT_CHARS = 256
MAX_CANDIDATES_PER_EVENT = 3
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB cap on provider replies
CATEGORIES = {"project", "preference", "fact", "codex-auto"}
DEFAULT_CATEGORY = "codex-auto"
OWNER_EVENT_STATUSES = {
    "NOT_FOUND",
    "ACCEPTED",
    "PENDING",
    "COMMITTED",
    "CANCELLED",
    "FAILED",
    "QUARANTINED",
}
OWNER_LOCAL_STATUSES = OWNER_EVENT_STATUSES | {"SUBMITTING", "NO_CANDIDATES", "UNKNOWN"}
OWNER_RETRYABLE_STATUSES = {"ACCEPTED", "PENDING"}
RESPONSE_CONTENT_ERROR = "extraction response lacks message content"

SECRETISH = re.compile(
    r"\bsk-[A-Za-z0-9_-]{20,}"  # OpenAI-style keys
    r"|\bgh[pousr]_[A-Za-z0-9]{16,}"  # classic GitHub tokens
    r"|\bgithub_pat_[A-Za-z0-9_]{22,}"  # fine-grained GitHub PATs
    r"|\bxox[aepsbr]-[A-Za-z0-9-]{10,}"  # Slack tokens
    r"|\bAKIA[0-9A-Z]{16}"  # AWS access key IDs
    r"|\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"  # bare bearer credentials
    r"|-----BEGIN[A-Za-z0-9 ]*-----"  # PEM blocks (incl. PRIVATE KEY headers)
    r"|[A-Za-z0-9+/]{40,}={0,2}(?=\s|$)"  # long base64-ish tokens
    r"|(?:API_?KEY|SECRET|TOKEN|PASSWORD|PASSWD|AUTH|CREDENTIAL)[=:]\s*\S+",
    re.IGNORECASE,
)

EXTRACTION_PROMPT = """\
You extract durable, portable memory candidates from ONE completed agent turn.
Return ONLY a JSON object:
{{"memories": [{{"text": str, "category": [str], "importance": float, \
"replacement_intent": bool, "replacement_context": str only for this candidate}}]}}.
Rules:
- At most {max_candidates} candidates; each text at most {max_text} characters.
- Only durable user facts or preferences; skip plans, code, secrets, links.
- Skip one-time calculations, temporary events, and content the user explicitly
  says not to remember or store. Do not repeat that content in a memory; return
  an empty list when nothing else is durable.
- Preserve the user's meaning; do not invent.
- replacement_intent is false by default. Set it true only when this user turn
  explicitly corrects a durable fact by naming both the old value and its
  replacement. Never set it for first mentions, restatements, or unchanged facts.
- If replacement_intent is true, set this candidate's replacement_context to
  the shortest exact old fact stated in this turn, not the whole turn. Each
  replacement candidate must have its own context; never reuse context across
  candidates. Do not infer conflicts with memories that are not present in this
  turn.
- INPUT FIDELITY: {fidelity_note}
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


def _failed_move_leftover(path, event) -> bool:
    """True when the extracted twin is the archived copy of this snapshot."""
    twin = runtime.read_json(runtime.extracted_dir() / path.name)
    return (
        isinstance(twin, dict)
        and twin.get("pending_cleanup_failed") is True
        and twin.get("stored_utc") == event.get("stored_utc")
    )


def _load_one_pending(path, mutate: bool, quarantined: list[str]):
    """Load one pending file, quarantining or reconciling it when needed."""
    event = runtime.read_json(path)
    if event is None or not isinstance(event, dict):
        renamed = runtime.quarantine_pending(path) if mutate else None
        quarantined.append(renamed or path.name)
        return None
    if event.get("status") != "pending":
        return None
    if _failed_move_leftover(path, event):
        if mutate:
            try:  # leftover of a failed move for this exact snapshot
                path.unlink()
            except OSError:
                pass
        return None
    event["_path"] = path
    event["_fingerprint"] = runtime.file_fingerprint(path)
    return event


def load_pending(mutate: bool = True) -> tuple[list[dict], list[str]]:
    """Load pending events; quarantine unreadable files and reconcile leftovers.

    Returns ``(events, quarantined)``. Unreadable files are renamed to
    ``*.corrupt`` only when ``mutate`` is set, so the default dry-run does not
    touch the journal. A pending file is removed only when its extracted twin
    is marked ``pending_cleanup_failed`` for the same ``stored_utc`` snapshot;
    a newer Stop redelivery with the same deterministic event id is kept for
    extraction. Events are ordered so never-failed events come first, then by
    retry count, so repeatedly failing events do not occupy every batch.
    """
    events: list[dict] = []
    quarantined: list[str] = []
    try:
        paths = sorted(runtime.pending_dir().glob("*.json"))
    except OSError:
        return events, quarantined
    for path in paths:
        event = _load_one_pending(path, mutate, quarantined)
        if event is not None:
            events.append(event)
    events.sort(
        key=lambda item: (
            bool(item.get("last_error")),
            int(item.get("attempts") or 0),
            item["_path"].name,
        )
    )
    return events, quarantined



def _turn_inputs(event: dict) -> dict:
    """Validate and collect the bounded turn inputs (raises on malformed shape)."""
    user_text = event.get("user_text")
    assistant_text = event.get("assistant_text")
    if not isinstance(user_text, dict) or not isinstance(user_text.get("excerpt"), str):
        raise ValueError("pending event has a malformed user_text field")
    if not isinstance(assistant_text, dict) or not isinstance(
        assistant_text.get("text"), str
    ):
        raise ValueError("pending event has a malformed assistant_text field")
    user_truncated = bool(user_text.get("truncated"))
    assistant_truncated = bool(assistant_text.get("truncated"))
    return {
        "user_excerpt": user_text["excerpt"],
        "assistant_text": assistant_text["text"],
        "user_truncated": user_truncated,
        "assistant_truncated": assistant_truncated,
    }


def build_prompt(event: dict) -> str:
    """Render the extraction prompt; surfaces input truncation to the model."""
    inputs = _turn_inputs(event)
    flags = []
    if inputs["user_truncated"]:
        flags.append("the USER input is TRUNCATED")
    if inputs["assistant_truncated"]:
        flags.append("the ASSISTANT input is TRUNCATED")
    if flags:
        fidelity_note = (
            "; ".join(flags).capitalize()
            + ". Do not extract any fact that depends on text missing from a "
            "TRUNCATED input; when in doubt, omit the candidate."
        )
    else:
        fidelity_note = "both inputs are complete"
    user_marked = inputs["user_excerpt"] + (
        " [TRUNCATED]" if inputs["user_truncated"] else ""
    )
    assistant_marked = inputs["assistant_text"] + (
        " [TRUNCATED]" if inputs["assistant_truncated"] else ""
    )
    return EXTRACTION_PROMPT.format(
        max_candidates=MAX_CANDIDATES_PER_EVENT,
        max_text=MAX_CANDIDATE_TEXT_CHARS,
        fidelity_note=fidelity_note,
        user_text=user_marked,
        assistant_text=assistant_marked,
    )


def _endpoint_is_loopback(base_url: str) -> bool:
    """True when the endpoint host is localhost or a loopback IP address."""
    host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _require_safe_endpoint(base_url: str) -> None:
    """Refuse plaintext transport to non-loopback endpoints before any send."""
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and _endpoint_is_loopback(base_url):
        return
    host = parsed.hostname or ""
    raise ValueError(
        "refusing to send staged turn text over "
        f"{parsed.scheme or 'unknown-scheme'}://{host}: non-loopback "
        "extraction endpoints must use https://"
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so extraction can only reach the validated endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "extraction endpoint redirects are refused",
            headers,
            fp,
        )


_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoRedirect(),
)


class ExtractionProvider:
    """OpenAI-compatible /chat/completions client (local Ollama default)."""

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        _require_safe_endpoint(base_url)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def extract(self, prompt: str):
        """POST the prompt to the configured provider and return its reply."""
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
        headers = {"Content-Type": "application/json"}
        key = _extraction_key()
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        with _OPENER.open(request, timeout=self.timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError(
                f"extraction response exceeds {MAX_RESPONSE_BYTES} bytes"
            )
        body = json.loads(raw.decode("utf-8"))
        return _parse_model_json(_response_content(body))


def _response_content(body) -> str:
    """Return the assistant content from an OpenAI-compatible response.

    Every level is shape-checked so a malformed reply becomes a per-event
    ValueError instead of an AttributeError that would abort the batch.
    """
    if not isinstance(body, dict):
        raise ValueError("extraction response is not an object")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(RESPONSE_CONTENT_ERROR)
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("extraction response has a malformed choice entry")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError(RESPONSE_CONTENT_ERROR)
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError(RESPONSE_CONTENT_ERROR)
    return content


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


def _inputs_truncated(source_event) -> bool:
    """True only when BOTH sides arrived clipped (candidates may rely on gaps)."""
    if not isinstance(source_event, dict):
        return False
    user_text = source_event.get("user_text")
    assistant_text = source_event.get("assistant_text")
    return (
        isinstance(user_text, dict)
        and bool(user_text.get("truncated"))
        and isinstance(assistant_text, dict)
        and bool(assistant_text.get("truncated"))
    )


def validate_candidates(document, source_event: dict) -> tuple[list[dict], list[str]]:
    """Enforce the shared Runtime candidate contract; return (good, rejected)."""
    good, rejected = [], []
    raw = document.get("memories")
    if not isinstance(raw, list):
        return good, ["reply memories is not a list"]
    inputs_truncated = _inputs_truncated(source_event)
    for raw_candidate in raw[:MAX_CANDIDATES_PER_EVENT]:
        error = _candidate_error(raw_candidate)
        if error:
            rejected.append(error)
            continue
        if inputs_truncated:
            rejected.append("candidate not admitted: event inputs truncated")
            continue
        candidate = {
            "text": raw_candidate["text"].strip(),
            "category": raw_candidate.get("category") or [DEFAULT_CATEGORY],
            "importance": float(raw_candidate.get("importance", 0.5)),
            "replacement_intent": raw_candidate.get("replacement_intent", False),
        }
        replacement_context = raw_candidate.get("replacement_context")
        if (
            candidate["replacement_intent"]
            and isinstance(replacement_context, str)
            and replacement_context.strip()
        ):
            replacement_context = replacement_context.strip()
            user_text = source_event.get("user_text") if isinstance(source_event, dict) else None
            user_excerpt = user_text.get("excerpt") if isinstance(user_text, dict) else None
            if not isinstance(user_excerpt, str) or replacement_context not in user_excerpt:
                rejected.append("replacement context not present in user input")
                continue
            candidate["replacement_context"] = replacement_context
        if candidate["replacement_intent"] and not candidate.get("replacement_context"):
            candidate["replacement_context_missing"] = True
        good.append(candidate)
    if len(raw) > MAX_CANDIDATES_PER_EVENT:
        rejected.append(
            f"{len(raw) - MAX_CANDIDATES_PER_EVENT} extra candidates dropped"
        )
    return good, rejected


def _candidate_error(candidate) -> str | None:
    """Return the rejection reason for one candidate, or None when it is valid."""
    if not isinstance(candidate, dict):
        return "candidate is not an object"
    allowed = {
        "text", "category", "importance", "replacement_intent", "replacement_context"
    }
    if set(candidate) - allowed:
        return "candidate has extra keys"
    text = candidate.get("text")
    if not isinstance(text, str) or not text.strip():
        return "candidate text empty"
    if len(text.strip()) > MAX_CANDIDATE_TEXT_CHARS:
        return "candidate text too long"
    if SECRETISH.search(text):
        return "candidate looks secret-shaped"
    replacement_intent = candidate.get("replacement_intent", False)
    if not isinstance(replacement_intent, bool):
        return "replacement intent invalid"
    replacement_context = candidate.get("replacement_context")
    if replacement_context is not None:
        if not isinstance(replacement_context, str):
            return "replacement context invalid"
        if len(replacement_context.strip()) > 300:
            return "replacement context too long"
        if SECRETISH.search(replacement_context):
            return "replacement context looks secret-shaped"
        if replacement_context.strip() and not replacement_intent:
            return "replacement context without replacement intent"
    category = candidate.get("category")
    if category is None:
        category = [DEFAULT_CATEGORY]
    if not isinstance(category, list) or not all(
        isinstance(item, str) and item and len(item) <= 64 for item in category
    ):
        return "candidate category invalid"
    try:
        importance = float(candidate.get("importance", 0.5))
    except (TypeError, ValueError, OverflowError):
        return "candidate importance invalid"
    if not 0.0 <= importance <= 1.0:
        return "candidate importance out of range"
    return None


def show_plan(outcomes, dropped_overflow: int, quarantined=()) -> None:
    """Print the dry-run plan (default): zero writes, zero mutations."""
    report = {
        "mode": "dry-run",
        "pending_events": len(outcomes),
        "dropped_overflow_events": dropped_overflow,
        "quarantined_pending_files": list(quarantined),
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


def _receipt_provenance() -> dict:
    """Provenance block stamped onto every admitted-candidate receipt."""
    return {**runtime.PROVENANCE, "plugin_version": runtime.PLUGIN_VERSION}


def _replacement_target(candidate: dict, admit) -> dict:
    """Locate the outdated memory a replacement candidate proposes to replace.

    Runs BEFORE the add so the new record cannot match itself. The top search
    hit is only a PROPOSAL: semantic search alone does not establish that the
    record is the fact being replaced, so deletion is gated on explicit
    operator approval (``--allow-replacement-deletes``).
    """
    context = candidate.get("replacement_context")
    if not isinstance(context, str) or not context.strip():
        return {"target_found": False, "note": "replacement context missing"}
    result = {"context": context[:300], "target_found": False}
    status, body, _err = admit("search", "--query", context)
    rows = []
    if status == 0:
        try:
            rows = json.loads(body).get("memories") or []
        except ValueError:
            rows = []
    if not rows:
        result["note"] = "no stored memory matched the replacement context"
        return result
    top = rows[0]
    target_id = top.get("id")
    if not isinstance(target_id, str) or not target_id:
        result["note"] = "search returned no usable record id"
        return result
    result["target_found"] = True
    result["proposed_record_id"] = target_id
    old_text = top.get("text")
    if isinstance(old_text, str):
        result["proposed_text"] = old_text[:300]
    return result


def _delete_replacement_target(target: dict, admit, approved: bool) -> dict:
    """Delete the proposed superseded memory when the operator approved it.

    Without approval the located proposal is recorded in the receipt only;
    the receipt always shows what was (or would be) replaced.
    """
    record_id = target.get("proposed_record_id")
    if not target.get("target_found") or not isinstance(record_id, str):
        return target
    if not approved:
        target["note"] = (
            "deletion not approved; rerun with --allow-replacement-deletes "
            "to delete the proposed target"
        )
        return target
    status, body, err = admit("delete", "--id", record_id)
    if status != 0:
        target["delete_error"] = runtime.safe_error(body, err)
    else:
        target["deleted"] = True
    return target


def _superseded_outcome(outcome) -> dict:
    """Report an event whose staged snapshot was overwritten before admission."""
    return {
        "event_id": outcome["event_id"],
        "status": "pending",
        "superseded": True,
        "admitted": [],
        "skipped": [],
        "rejected": outcome["rejected"],
        "extraction_error": outcome.get("extraction_error"),
        "last_error": None,
    }


def _add_candidate(candidate, admit) -> tuple[object, str | None]:
    """Add one candidate; return its record id and an optional error."""
    status, body, err = admit("add", "--text", candidate["text"])
    if status != 0:
        return None, runtime.safe_error(body, err)
    try:
        return json.loads(body).get("id"), None
    except ValueError:
        return None, None


def _delete_after_add(candidate, replacement, admit, approved, errors):
    """Apply a replacement delete without losing the successful add receipt."""
    if not candidate.get("replacement_intent"):
        return replacement
    try:
        return _delete_replacement_target(replacement or {}, admit, approved)
    except runtime.HookError as error:
        # The add already succeeded: record the delete failure on the receipt
        # and keep the event pending so the retry can revisit it.
        replacement = replacement if isinstance(replacement, dict) else {}
        replacement["delete_error"] = str(error)
        errors.append(str(error))
        return replacement


def _receipt(candidate, record_id, replacement) -> dict:
    """Build the durable admitted-candidate receipt."""
    admitted = {
        "text": candidate["text"],
        "record_id": record_id,
        "category": candidate["category"],
        "importance": candidate["importance"],
        "replacement_intent": candidate["replacement_intent"],
        "provenance": _receipt_provenance(),
    }
    if replacement is not None:
        admitted["replacement"] = replacement
    if candidate.get("replacement_context_missing"):
        admitted["replacement_context_missing"] = True
    return admitted


def _admit_candidate(candidate, admit, approved, event_state, errors) -> None:
    """Admit one candidate under the admission lock, or record why not."""
    try:
        # One lock around search + (replacement) + add: concurrent admissions
        # for the same candidate cannot both miss the dedupe.
        with runtime.exclusive_lock("admit"):
            if is_duplicate(candidate["text"], admit):
                event_state["skipped"].append(
                    {"text": candidate["text"], "reason": "duplicate"}
                )
                return
            replacement = None
            if candidate.get("replacement_intent"):
                replacement = _replacement_target(candidate, admit)
            record_id, error = _add_candidate(candidate, admit)
            if error is not None:
                errors.append(error)
                return
            replacement = _delete_after_add(
                candidate, replacement, admit, approved, errors
            )
    except runtime.HookError as error:
        errors.append(str(error))
        return
    event_state["admitted"].append(_receipt(candidate, record_id, replacement))


def _already_admitted_texts(path) -> set[str]:
    """Texts of receipts a previous attempt already admitted for this event."""
    previous = runtime.read_json(path)
    rows = previous.get("candidates") if isinstance(previous, dict) else []
    return {
        str(item.get("text", "")).strip()
        for item in rows or []
        if isinstance(item, dict)
    }


def _admit_event(outcome, admit, allow_replacement_deletes: bool = False) -> dict:
    """Admit one staged event's candidates and persist its post-run state.

    The staged snapshot is fingerprint-checked again inside
    :func:`finalize_event` under the pending lock, so a Stop redelivery that
    lands between loading and finalizing can never be stamped with this
    run's status.
    """
    errors = []
    path = outcome["_path"]
    # Stale-snapshot guard: a concurrent Stop redelivery may have overwritten
    # this file after it was loaded. Admit nothing from the old content and
    # leave the newer snapshot pending untouched.
    if runtime.file_fingerprint(path) != outcome.get("_fingerprint"):
        return _superseded_outcome(outcome)
    event_state = {
        "event_id": outcome["event_id"],
        "admitted": [],
        "skipped": [],
        "rejected": outcome["rejected"],
    }
    already_admitted = _already_admitted_texts(path)
    if outcome.get("extraction_error"):
        errors.append(outcome["extraction_error"])
    for candidate in outcome["candidates"]:
        if candidate["text"].strip() in already_admitted:
            event_state["skipped"].append(
                {"text": candidate["text"], "reason": "already admitted"}
            )
            continue
        _admit_candidate(
            candidate, admit, allow_replacement_deletes, event_state, errors
        )
    if errors:
        event_state["last_error"] = " | ".join(errors)[:600]
    new_status = "extracted" if not errors else "pending"
    finalize_event(
        path,
        event_state,
        new_status,
        loaded_fingerprint=outcome.get("_fingerprint", ""),
    )
    return {
        "event_id": outcome["event_id"],
        "status": new_status,
        "admitted": [item["text"] for item in event_state["admitted"]],
        "skipped": event_state["skipped"],
        "rejected": event_state["rejected"],
        "extraction_error": outcome.get("extraction_error"),
        "last_error": event_state.get("last_error"),
    }



def admit_all(
    outcomes, *, runtime_home_cli=None, allow_replacement_deletes: bool = False
) -> dict:
    """Confirm path: admit validated candidates through the Runtime CLI.

    The runtime callable resolves at call time (never captured as a default
    argument) so operator/test substitution behaves predictably. A failure on
    one event is recorded and later events still run.
    """
    admit = runtime_home_cli or runtime.call_runtime
    results = []
    for outcome in outcomes:
        try:
            results.append(
                _admit_event(outcome, admit, allow_replacement_deletes)
            )
        except runtime.HookError as error:
            results.append(_failed_outcome(outcome, str(error)))
        except OSError as error:
            results.append(_failed_outcome(outcome, f"storage failure: {error}"))
    return {"mode": "confirm", "events": results}


def _failed_outcome(outcome, message: str) -> dict:
    """Build the reported shape for an event whose admission failed early."""
    return {
        "event_id": outcome.get("event_id", ""),
        "status": "pending",
        "admitted": [],
        "skipped": [],
        "rejected": outcome.get("rejected", []),
        "extraction_error": outcome.get("extraction_error"),
        "last_error": message[:600],
    }


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


def validate_owner_url(value: str) -> str:
    """Require a credential-free HTTPS base URL for the opt-in Owner route."""
    parsed = urllib.parse.urlsplit(value.strip())
    try:
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        valid_port = False
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not valid_port
    ):
        raise ValueError(
            "Owner lifecycle URL must be HTTPS without credentials, query, or fragment"
        )
    return value.strip().rstrip("/")


def _owner_source_digest(event: dict) -> str:
    """Hash the staged source snapshot without sending it to the Owner."""
    source = {
        key: event.get(key)
        for key in (
            "event_id",
            "session_id",
            "turn_id",
            "user_text",
            "assistant_text",
            "user_truncated",
            "assistant_truncated",
        )
    }
    raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _owner_request(url: str, token_env: str, ca_file, action: str, payload: dict) -> dict:
    """Use Runtime's HTTPS client; the token value stays in its environment."""
    args = [
        "remote-event",
        "--url",
        url,
        "--token-env",
        token_env,
        "--action",
        action,
    ]
    if ca_file is not None:
        args.extend(("--ca-file", str(ca_file)))
    code, stdout, _stderr = runtime.call_runtime(
        *args,
        timeout=180.0,
        input_text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    if code != 0:
        raise runtime.HookError(f"Owner lifecycle {action} request failed")
    try:
        result = json.loads(stdout)
    except (TypeError, ValueError):
        raise runtime.HookError("Owner lifecycle returned an invalid receipt") from None
    if (
        not isinstance(result, dict)
        or result.get("event_id") != payload.get("event_id")
        or not isinstance(result.get("status"), str)
        or result.get("status") not in OWNER_EVENT_STATUSES
    ):
        raise runtime.HookError("Owner lifecycle returned an invalid receipt")
    return result


def _owner_candidate_count(receipt: dict) -> int:
    """Return a bounded local candidate count or reject a malformed receipt."""
    value = receipt.get("candidate_count", 0)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_CANDIDATES_PER_EVENT
    ):
        raise ValueError("Local Owner lifecycle receipt has an invalid candidate count")
    return value


def _is_owner_local_status(value) -> bool:
    """Reject non-string or unknown statuses before using local receipt data."""
    return isinstance(value, str) and value in OWNER_LOCAL_STATUSES


def _owner_candidate_payload(event: dict, candidates: list[dict]) -> tuple[dict, list[str]]:
    """Map validated candidates to extraction-v1 without forwarding turn text."""
    accepted = []
    rejected = []
    replacements = []
    for candidate in candidates:
        item = {
            "text": candidate["text"],
            "category": candidate["category"],
            "importance": candidate["importance"],
            "replacement_intent": candidate["replacement_intent"],
        }
        if candidate["replacement_intent"]:
            context = candidate.get("replacement_context")
            if not isinstance(context, str) or not context.strip():
                rejected.append("replacement candidate omitted: exact context is required")
                continue
            replacements.append((item, context.strip()))
        else:
            accepted.append(item)
    if len(replacements) > 1:
        rejected.append(
            f"{len(replacements)} replacement candidates omitted: Owner schema supports one context per event"
        )
    elif replacements:
        item, context = replacements[0]
        accepted.append(item)
    payload = {
        "event_id": event["event_id"],
        "session_id": event["session_id"],
        "kind": "turn_completed",
        "candidate_schema": "qdrant-memory/extraction-v1",
        "candidates": accepted,
    }
    if len(replacements) == 1:
        payload["replacement_context"] = context
    return payload, rejected


def _persist_owner_intent(event: dict, receipt: dict) -> bool:
    """Record a content-free retry marker before contacting the Owner."""
    path = event["_path"]
    with runtime.exclusive_lock("pending"):
        if runtime.file_fingerprint(path) != event.get("_fingerprint"):
            return False
        current = runtime.read_json(path)
        if not isinstance(current, dict) or current.get("event_id") != event.get("event_id"):
            return False
        current["owner_lifecycle"] = receipt
        runtime.write_json_private(path, current)
        event["owner_lifecycle"] = receipt
        event["_fingerprint"] = runtime.file_fingerprint(path)
    return True


def _finish_owner_event(
    event: dict,
    new_status: str,
    *,
    source_digest: str,
    owner_status: str,
    candidate_count: int = 0,
    rejected=(),
    error: str | None = None,
    action: str,
) -> dict:
    """Persist Owner status through the existing staged-event receipt path."""
    event_state = {
        "event_id": event.get("event_id", ""),
        "admitted": [],
        "skipped": [],
        "rejected": list(rejected),
    }
    if error:
        event_state["last_error"] = error[:600]
    receipt = {
        "event_id": event.get("event_id", ""),
        "source_sha256": source_digest,
        "status": owner_status,
        "candidate_count": candidate_count,
        "action": action,
        "updated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    prior_receipt = event.get("owner_lifecycle")
    if isinstance(prior_receipt, dict) and isinstance(
        prior_receipt.get("candidate_sha256"), str
    ):
        receipt["candidate_sha256"] = prior_receipt["candidate_sha256"]
    finalize_event(
        event["_path"],
        event_state,
        new_status,
        loaded_fingerprint=event.get("_fingerprint", ""),
        owner_receipt=receipt,
    )
    return {
        "event_id": event.get("event_id", ""),
        "status": new_status,
        "owner_status": owner_status,
        "candidate_count": candidate_count,
        "rejected": list(rejected),
        "last_error": error,
    }


def _finish_owner_conflict(event: dict, message: str) -> dict:
    """Keep the earlier Owner receipt intact when snapshots cannot be matched."""
    event_state = {
        "event_id": event.get("event_id", ""),
        "admitted": [],
        "skipped": [],
        "rejected": [],
        "last_error": message[:600],
    }
    finalize_event(
        event["_path"],
        event_state,
        "pending",
        loaded_fingerprint=event.get("_fingerprint", ""),
    )
    prior = event.get("owner_lifecycle")
    try:
        candidate_count = _owner_candidate_count(prior) if isinstance(prior, dict) else 0
    except ValueError:
        candidate_count = 0
    owner_status = (
        prior.get("status", "UNKNOWN")
        if isinstance(prior, dict) and _is_owner_local_status(prior.get("status"))
        else "UNKNOWN"
    )
    return {
        "event_id": event.get("event_id", ""),
        "status": "pending",
        "owner_status": owner_status,
        "candidate_count": candidate_count,
        "rejected": [],
        "last_error": message,
    }


def _process_owner_event(event: dict, provider, *, url: str, token_env: str, ca_file) -> dict:
    """Extract once, then submit or retry one idempotent Owner event."""
    source_digest = _owner_source_digest(event)
    event_id = event.get("event_id", "")
    prior = event.get("owner_lifecycle")
    if prior is not None and not isinstance(prior, dict):
        return _finish_owner_conflict(
            event, "Local Owner lifecycle receipt is malformed; review before retrying"
        )
    prior_count = 0
    if isinstance(prior, dict):
        try:
            prior_count = _owner_candidate_count(prior)
        except ValueError:
            return _finish_owner_conflict(
                event, "Local Owner lifecycle receipt is malformed; review before retrying"
            )
        if prior.get("event_id") != event_id:
            return _finish_owner_conflict(
                event, "Local Owner lifecycle receipt does not match this pending event"
            )
        if not _is_owner_local_status(prior.get("status")):
            return _finish_owner_conflict(
                event, "Local Owner lifecycle receipt has an unknown status; review before retrying"
            )
    if isinstance(prior, dict) and prior.get("action") in {"conflict", "reconcile"}:
        return _finish_owner_conflict(
            event, "Owner lifecycle receipt requires manual reconciliation"
        )
    if isinstance(prior, dict) and prior.get("source_sha256") != source_digest:
        return _finish_owner_conflict(
            event,
            "Owner already has a receipt for an earlier snapshot of this event; review the pending turn",
        )

    status_result = _owner_request(url, token_env, ca_file, "status", {"event_id": event_id})
    remote_status = status_result["status"]
    if remote_status != "NOT_FOUND":
        if not isinstance(prior, dict) or prior.get("event_id") != event_id:
            return _finish_owner_conflict(
                event,
                "Owner has an event receipt without a matching local intent; review before retrying",
            )
        if remote_status == "COMMITTED":
            return _finish_owner_event(
                event,
                "extracted",
                source_digest=source_digest,
                owner_status=remote_status,
                candidate_count=prior_count,
                action="status",
            )
        if remote_status == "CANCELLED":
            return _finish_owner_event(
                event,
                "pending",
                source_digest=source_digest,
                owner_status=remote_status,
                candidate_count=prior_count,
                error="Owner event was cancelled; create a new capture after review",
                action="status",
            )
        if remote_status == "QUARANTINED":
            return _finish_owner_event(
                event,
                "pending",
                source_digest=source_digest,
                owner_status=remote_status,
                candidate_count=prior_count,
                error="Owner quarantined this event; an Owner operator must recover it before retrying",
                action="status",
            )
        if remote_status == "FAILED":
            return _finish_owner_event(
                event,
                "pending",
                source_digest=source_digest,
                owner_status=remote_status,
                candidate_count=prior_count,
                error="Owner event failed; a Runtime operator must recover it before retrying",
                action="status",
            )
        if remote_status not in OWNER_RETRYABLE_STATUSES:
            return _finish_owner_event(
                event,
                "pending",
                source_digest=source_digest,
                owner_status=remote_status,
                candidate_count=prior_count,
                error=f"Owner returned unsupported event status: {remote_status[:80]}",
                action="status",
            )
        result = _owner_request(url, token_env, ca_file, "retry", {"event_id": event_id})
        final_status = result["status"]
        if final_status == "COMMITTED":
            error = None
        elif final_status == "QUARANTINED":
            error = "Owner quarantined this event; an Owner operator must recover it before retrying"
        else:
            error = f"Owner retry returned {final_status}"
        return _finish_owner_event(
            event,
            "extracted" if final_status == "COMMITTED" else "pending",
            source_digest=source_digest,
            owner_status=final_status,
            candidate_count=prior_count,
            error=error,
            action="retry",
        )

    if isinstance(prior, dict) and prior.get("status") in {"COMMITTED", "CANCELLED"}:
        return _finish_owner_conflict(
            event,
            "Local Owner receipt conflicts with the Owner status; review before retrying",
        )
    try:
        document = provider.extract(build_prompt(event))
        candidates, rejected = validate_candidates(document, event)
    except (
        ValueError,
        KeyError,
        AttributeError,
        OverflowError,
        OSError,
        http.client.HTTPException,
    ) as error:
        return _finish_owner_event(
            event,
            "pending",
            source_digest=source_digest,
            owner_status="NOT_FOUND",
            error=redact(str(error))[:300],
            action="extract",
        )
    payload, payload_rejections = _owner_candidate_payload(event, candidates)
    rejected = [*rejected, *payload_rejections]
    if not payload["candidates"]:
        return _finish_owner_event(
            event,
            "extracted",
            source_digest=source_digest,
            owner_status="NO_CANDIDATES",
            rejected=rejected,
            action="empty",
        )
    intent = {
        "event_id": event_id,
        "source_sha256": source_digest,
        "candidate_sha256": hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "status": "SUBMITTING",
        "candidate_count": len(payload["candidates"]),
        "action": "submit",
        "updated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    if not _persist_owner_intent(event, intent):
        return _superseded_outcome({"event_id": event_id})
    result = _owner_request(url, token_env, ca_file, "submit", payload)
    final_status = result["status"]
    if final_status == "COMMITTED":
        error = None
    elif final_status == "QUARANTINED":
        error = "Owner quarantined this event; an Owner operator must recover it before retrying"
    else:
        error = f"Owner submit returned {final_status}"
    return _finish_owner_event(
        event,
        "extracted" if final_status == "COMMITTED" else "pending",
        source_digest=source_digest,
        owner_status=final_status,
        candidate_count=len(payload["candidates"]),
        rejected=rejected,
        error=error,
        action="submit",
    )


def admit_owner_all(events, provider, *, url: str, token_env: str, ca_file) -> dict:
    """Run the explicitly opted-in Owner candidate flow for bounded pending events."""
    results = []
    for event in events:
        try:
            results.append(
                _process_owner_event(
                    event, provider, url=url, token_env=token_env, ca_file=ca_file
                )
            )
        except (
            runtime.HookError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            http.client.HTTPException,
        ) as error:
            prior = event.get("owner_lifecycle")
            try:
                candidate_count = (
                    _owner_candidate_count(prior) if isinstance(prior, dict) else 0
                )
            except ValueError:
                candidate_count = 0
            owner_status = (
                prior.get("status", "UNKNOWN")
                if isinstance(prior, dict)
                and _is_owner_local_status(prior.get("status"))
                else "UNKNOWN"
            )
            results.append(
                _finish_owner_event(
                    event,
                    "pending",
                    source_digest=_owner_source_digest(event),
                    owner_status=owner_status,
                    candidate_count=candidate_count,
                    error=redact(str(error))[:300],
                    action="error",
                )
            )
    return {"mode": "confirm-owner", "events": results}


def _merge_admitted(previous, admitted) -> list[dict]:
    """Merge this run's admitted receipts into any earlier ones (retry-safe)."""
    merged: dict = {}
    for item in previous if isinstance(previous, list) else []:
        if isinstance(item, dict):
            merged.setdefault(item.get("record_id") or item.get("text"), item)
    for item in admitted:
        merged.setdefault(item.get("record_id") or item["text"], item)
    return list(merged.values())


def finalize_event(
    path,
    event_state,
    new_status,
    loaded_fingerprint: str = "",
    owner_receipt: dict | None = None,
) -> None:
    """Persist the post-admission event state into its staged file.

    Runs under the pending lock (the same one :func:`lifecycle_runtime.write_pending_event`
    uses) and re-checks the snapshot fingerprint: if a Stop redelivery
    replaced the staged content while this run processed the older snapshot,
    the newer turn stays pending untouched and only this run's durable
    receipts (admitted records, skips, refusals) are merged into it, so the
    next run re-extracts the newer content and deduplicates against them.
    """
    skipped = [
        {"text": item["text"], "reason": item["reason"]}
        for item in event_state["skipped"]
    ]
    rejected = event_state.get("rejected", [])
    with runtime.exclusive_lock("pending"):
        event = runtime.read_json(path) or {}
        content_changed = (
            bool(loaded_fingerprint)
            and runtime.file_fingerprint(path) != loaded_fingerprint
        )
        if content_changed:
            merged = _merge_admitted(event.get("candidates"), event_state["admitted"])
            if merged or skipped or rejected or owner_receipt:
                event["candidates"] = merged
                event["skipped"] = skipped
                event["rejected"] = rejected
                if owner_receipt:
                    event["owner_lifecycle"] = owner_receipt
                runtime.write_json_private(path, event)
            return
        event["status"] = new_status
        event["processed_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="milliseconds"
        )
        # Retry semantics: keep every earlier admitted receipt and its record ID;
        # this run's receipts are merged in without duplicating entries.
        event["candidates"] = _merge_admitted(
            event.get("candidates"), event_state["admitted"]
        )
        event["skipped"] = skipped
        event["rejected"] = rejected
        if owner_receipt:
            event["owner_lifecycle"] = owner_receipt
        if event_state.get("last_error"):
            event["last_error"] = event_state["last_error"]
            event["attempts"] = int(event.get("attempts") or 0) + 1
        else:
            event.pop("last_error", None)  # the retry resolved the failure
            event.pop("attempts", None)
        destination_parent = (
            runtime.extracted_dir() if new_status == "extracted" else runtime.pending_dir()
        )
        destination = destination_parent / path.name
        runtime.write_json_private(destination, event)
        if path != destination:
            try:
                path.unlink()
            except OSError:
                # Recoverable move: mark the archived copy; the next load
                # reconciles the leftover pending duplicate before processing.
                event["pending_cleanup_failed"] = True
                runtime.write_json_private(destination, event)


def main(argv=None) -> None:
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
        help="admit candidates (default: dry-run only)",
    )
    parser.add_argument(
        "--owner-lifecycle-url",
        help="opt in to submit validated candidates to a protected HTTPS Runtime Owner",
    )
    parser.add_argument(
        "--owner-token-env",
        default="QDRANT_MEMORY_REMOTE_TOKEN",
        help="environment variable name holding the Owner token",
    )
    parser.add_argument(
        "--owner-ca-file",
        type=Path,
        help="optional CA bundle for the protected HTTPS Owner",
    )
    parser.add_argument(
        "--allow-replacement-deletes",
        action="store_true",
        help="during --confirm, delete the superseded memory located by a "
        "candidate's replacement context (default: record the proposed "
        "target in the receipt without deleting)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="process at most N pending events this run",
    )
    args = parser.parse_args(argv)

    owner_url = None
    if args.owner_lifecycle_url:
        try:
            if not args.confirm:
                raise ValueError("Owner lifecycle requires --confirm")
            if args.allow_replacement_deletes:
                raise ValueError(
                    "--allow-replacement-deletes applies only to the local Runtime path"
                )
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", args.owner_token_env):
                raise ValueError("Owner token option must be an environment variable name")
            if args.owner_ca_file is not None and not args.owner_ca_file.is_file():
                raise ValueError("Owner CA file must name an existing file")
            owner_url = validate_owner_url(args.owner_lifecycle_url)
        except ValueError as error:
            print(json.dumps({"error": redact(str(error))}), file=sys.stderr)
            raise SystemExit(2) from None
    elif args.owner_ca_file is not None or args.owner_token_env != "QDRANT_MEMORY_REMOTE_TOKEN":
        print(json.dumps({"error": "Owner TLS and token options require --owner-lifecycle-url"}), file=sys.stderr)
        raise SystemExit(2)

    try:  # unsafe endpoint configuration fails before anything is read or sent
        provider = ExtractionProvider(args.base_url, args.model)
    except ValueError as error:
        print(json.dumps({"error": redact(str(error))}), file=sys.stderr)
        raise SystemExit(2) from None

    events, quarantined = load_pending(mutate=args.confirm)
    if quarantined:
        print(
            json.dumps({"quarantined_pending_files": quarantined}), file=sys.stderr
        )
    events = events[: max(args.limit, 0)]
    dropped_overflow = runtime.count_overflow_marker()
    if not events:
        print(
            json.dumps(
                {
                    "mode": "dry-run" if not args.confirm else "confirm",
                    "pending_events": 0,
                    "dropped_overflow_events": dropped_overflow,
                    "quarantined_pending_files": quarantined,
                }
            )
        )
        return
    if owner_url:
        result = admit_owner_all(
            events,
            provider,
            url=owner_url,
            token_env=args.owner_token_env,
            ca_file=args.owner_ca_file,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    remote = not _endpoint_is_loopback(args.base_url)
    outcomes = []
    for event in events:
        outcome = {
            "event_id": event.get("event_id", ""),
            "_path": event["_path"],
            "_fingerprint": event.get("_fingerprint", ""),
            "candidates": [],
            "rejected": [],
        }
        try:
            if not args.confirm and remote:
                raise ValueError(
                    "dry-run does not send staged turn text to a remote "
                    "provider; rerun with --confirm to consent"
                )
            document = provider.extract(build_prompt(event))
            good, rejected = validate_candidates(document, event)
            outcome["candidates"] = good
            outcome["rejected"] = rejected
        except (
            ValueError,
            KeyError,
            AttributeError,
            OverflowError,
            OSError,
            http.client.HTTPException,
        ) as error:
            outcome["extraction_error"] = redact(str(error))[:300]
        outcomes.append(outcome)
    if args.confirm:
        result = admit_all(
            outcomes, allow_replacement_deletes=args.allow_replacement_deletes
        )
    else:
        show_plan(outcomes, dropped_overflow, quarantined)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
