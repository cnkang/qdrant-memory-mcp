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
import http.client
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import lifecycle_runtime as runtime  # noqa: E402

MAX_CANDIDATE_TEXT_CHARS = 256
MAX_CANDIDATES_PER_EVENT = 3
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB cap on provider replies
CATEGORIES = {"project", "preference", "fact", "codex-auto"}
DEFAULT_CATEGORY = "codex-auto"
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
"replacement_intent": bool}}], "replacement_context": "<only if any candidate \
has replacement_intent true>"}}.
Rules:
- At most {max_candidates} candidates; each text at most {max_text} characters.
- Only durable user facts or preferences; skip plans, code, secrets, links.
- Preserve the user's meaning; do not invent.
- replacement_intent is false by default. Set it true only when this user turn
  explicitly corrects a durable fact by naming both the old value and its
  replacement. Never set it for first mentions, restatements, or unchanged facts.
- If replacement_intent is true, set replacement_context to the shortest exact
  old fact stated in this turn, not the whole turn. Do not infer conflicts with
  memories that are not present in this turn.
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
    replacement_context = document.get("replacement_context")
    if not isinstance(raw, list):
        return good, ["reply memories is not a list"]
    if not isinstance(replacement_context, (str, type(None))):
        replacement_context = None
    inputs_truncated = _inputs_truncated(source_event)
    for candidate in raw[:MAX_CANDIDATES_PER_EVENT]:
        error = _candidate_error(candidate)
        if error:
            rejected.append(error)
            continue
        if inputs_truncated:
            rejected.append("candidate not admitted: event inputs truncated")
            continue
        candidate = {
            "text": candidate["text"].strip(),
            "category": candidate.get("category") or [DEFAULT_CATEGORY],
            "importance": float(candidate.get("importance", 0.5)),
            "replacement_intent": bool(candidate.get("replacement_intent", False)),
        }
        if candidate["replacement_intent"] and isinstance(replacement_context, str):
            candidate["replacement_context"] = replacement_context
        if candidate["replacement_intent"] and not isinstance(replacement_context, str):
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
    path, event_state, new_status, loaded_fingerprint: str = ""
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
            if merged or skipped or rejected:
                event["candidates"] = merged
                event["skipped"] = skipped
                event["rejected"] = rejected
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
        help="admit candidates via Runtime add (default: dry-run only)",
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
