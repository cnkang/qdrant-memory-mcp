# Qdrant Memory lifecycle experiment (Mode B) — auto-capture preview

**Status: experimental local preview. NOT public-directory material.**

OpenAI documents plugin lifecycle hooks for **manually installed** plugins in
Codex desktop, and states that *"Plugins containing lifecycle hooks aren't
eligible for the public plugin directory"* and that they *"must be removed
before public directory submission"*
([Build plugins](https://developers.openai.com/plugins/build/plugins),
[Submission](https://developers.openai.com/plugins/deploy/submission)). The
hooks event contract is documented at
[Codex hooks](https://learn.chatgpt.com/docs/hooks).

This directory is the separately installed, clearly labeled experiment. The
repo's public plugin at `plugins/qdrant-memory` contains no hooks and keeps its
public-directory eligibility; repository tests assert the published package
stays hook-free.

## Product positioning (explicit)

**Qdrant Memory is the cross-agent durable memory layer** (Codex, Hermes, DSH,
OpenCode…). **Codex native memories remain the per-client local context; the
two coexist by design and overlap is acceptable.** This preview never reads or
writes Codex native storage (there is no public API), never disables it, and
adds new durable facts only into the one existing Runtime profile shared by
all agents.

## Pipeline (recalled facts / explicit saves / staged turns)

| Stage | Component | Writes | Consent |
|---|---|---|---|
| Recall | `SessionStart` (`startup\|resume\|clear\|compact\|fork`) → `session_recall.py` | none (read-only `search`; `additionalContext` injection capped by `additionalContextLimit`) | hook trust review |
| Explicit save | `UserPromptSubmit` → `user_prompt_capture.py` | **one** Runtime `add` for a line starting with `remember:` (≤512 chars, verbatim) | user typed the directive |
| Staging (auto) | `UserPromptSubmit` stages the turn's user text → `Stop` (`async`, no latency) `turn_capture.py` pairs it with `last_assistant_message` into one bounded local snapshot | local JSON only: `profile/events/codex/pending/` (0600; user excerpt ≤2 KiB, assistant ≤8 KiB; deterministic `event_id`; ring cap 300 pending; overflow counted, nothing dropped silently) | hook trust review; removable at any time by deleting staged files |
| Extraction | `extract_pending.py` — **operator-run, not a hook** | with the default `dry-run`: zero writes. `--confirm`: Runtime `add` per validated candidate (`extraction-v1` contract: bound text ≤256 chars, importance 0..1, ≤3 per turn, secret-shaped text refused, category/provenance retained in the event file) | the confirm invocation itself; provider is **local Ollama by default** (`http://127.0.0.1:11434/v1`); any OpenAI-compatible endpoint requires explicit `--base-url/--model` and, if needed, `EXTRACTION_API_KEY` from the environment (never an argument) |
| Cleanup | `SessionEnd` → `prune_scratch.py` (≤3 s) | expires unpaired pairing scratch (48 h TTL) | none |

Unpaired/interrupted turns are simply not captured. Re-running a Stop for the
same turn overwrites its own event (idempotence). Failures never block the
turn: capture failures are silent; extraction failures keep the event
`pending` with a recorded `last_error` for the next run.

`Stop`-based **extraction** (an automatic LLM call inside the session)
is still not part of the hooks: extraction is the operator's explicit command
so that its consent, provider and budget decisions are visible. The eventual
shared-Runtime route after Runtime 0.6.1 publishes is submission of validated
candidates to the Owner `qdrant-memory/extraction-v1` endpoint (durable
receipts + relation review reused from the DSH native design); the local
`add` path here is the pre-0.6.1 staging behavior and its receipts come from
the existing ledger.

## Privacy and retention facts

- Snapshots stay on this machine under the configured profile
  (`events/codex/`); 0600 files, 0700 directories; nothing is transmitted
  except what the extraction provider receives during the operator's explicit
  `confirm` run (local Ollama by default).
- `codex-plugin remove` (the preview plugin) and `uninstall` never delete the
  profile, staged events, extracted events, or stored memories.
- Purge paths: delete `profile/events/codex/` (aborts staged content before
  extraction) or use Runtime-scoped deletion for stored memories. Extraction
  decisions (admitted / skipped / refused reasons) are recorded in each
  event's file.
- No telemetry, no credential reading; hook diagnostics never include turn
  content.

## Install (manual, local)

```sh
codex plugin marketplace add <repo>/integrations/codex-lifecycle
codex plugin add qdrant-memory-lifecycle@cnkang-lifecycle-preview
# then open /hooks in the CLI (desktop: Settings → Hooks) and trust the four hooks
```

Requirements: the qdrant-memory Codex plugin (main plugin) installed and set
up (profile at `~/.qdrant-memory/codex/profile` or the documented
`QDRANT_MEMORY_CODEX_*` overrides), plus `python3` on POSIX or the `py -3`
launcher on Windows for hook commands.

## Extraction usage

```sh
# plan only (default; zero writes):
python3 integrations/codex-lifecycle/plugin/hooks/extract_pending.py \
  --model qwen3-embedding:4b --limit 25
# admit facts through the local Runtime:
python3 integrations/codex-lifecycle/plugin/hooks/extract_pending.py \
  --model <model> --confirm
```

Ollama must already serve the chosen model locally; the OpenAI-compatible
client calls `POST {base_url}/chat/completions` with `temperature 0` and a
strict JSON contract, and refuses empty/oversized/secret-shaped candidates.

> **0.165.0 caveat:** the preview manifest installs, but we have not observed
> 0.165.0 register these file-backed hook definitions for trust review or fire
> them in a session. Treat the install as a manifest-level preview; verify
> registration in your client before relying on recall or `remember:` capture.

## Verification status (2026-11-09)

| Check | Result |
|---|---|
| Handler units: scratch staging, pairing, byte caps, deterministic event IDs, idempotent overwrite, overflow marker, PLUGIN_DATA precedence, no-Runtime-invocation by capture, TTL prune, extraction validation (extra keys, secret-shaped, oversized, importance range), dry-run immutability, dedupe skip, failure keeps `pending` with recorded error | **PASS** (`tests/test_codex_lifecycle_hooks.py`, 29 cases, macOS arm64) |
| Real-Runtime round trip: Stop capture → stub extractor → `--confirm` → real Runtime `add` in the shared profile → Runtime `search` finds the record → pending emptied | **PASS** (`tests/test_codex_capture_integration.py`) |
| Repository marketplace accepts the hooks plugin manifest from the real Codex CLI 0.165.0 (`plugin add`/`mcp list`/`remove`) | **PASS** (per the readiness branch evidence; hooks cache resolution verified) |
| A real trust-reviewed Codex session firing all four hooks | **NOT VERIFIED** — needs a subscribed, hook-enabled client; do not treat this preview as verified until then |
| Extraction quality with real local models | **NOT VERIFIED** (uses a stub in tests; run `--limit 1 --dry-run` first on real data) |
| `Stop`-based in-session extraction (Route A) | **NOT IMPLEMENTED** by design (see pipeline note) |
| Public-directory eligibility of this directory | **NOT APPLICABLE** — hooks are ineligible for public submission per official docs |
