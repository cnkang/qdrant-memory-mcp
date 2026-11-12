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
| Explicit save | `UserPromptSubmit` → `user_prompt_capture.py` | **one** Runtime `add` for a line starting with `remember:` or `remember：` (≤512 chars, trailing whitespace preserved) | user typed the directive |
| Staging (auto) | `UserPromptSubmit` stages the turn's user text → `Stop` (`async`, no latency) `turn_capture.py` pairs it with `last_assistant_message` into one bounded local snapshot | local JSON only: `profile/events/codex/pending/` (0600; user excerpt ≤2 KiB, assistant ≤8 KiB; deterministic `event_id`; ring cap 300 pending under a profile-local lock — only newly added events count and an existing event_id always overwrites; overflow counted, nothing dropped silently) | hook trust review; removable at any time by deleting staged files |
| Extraction | `extract_pending.py` — **operator-run, not a hook** | with the default `dry-run`: zero writes and **no remote provider calls** (loopback providers only). `--confirm` uses the local Runtime `add` path. The explicit `--owner-lifecycle-url https://…` option instead submits only validated candidate fields through Runtime 0.6.1 `remote-event`; it never sends the raw turn, scope IDs, or token value. Owner lifecycle must be enabled and authorized by the protected Runtime grant. Both paths enforce the `extraction-v1` contract (text ≤256 chars, importance 0..1, ≤3 candidates per turn, secret-shaped text refused). Owner receipts are durable and retries use only the event ID; source hashes detect a changed Stop snapshot and leave it pending for review. More than one replacement candidate in a turn is rejected because the Owner schema carries one replacement context. Failures keep the event `pending` with a retryable status and never block Codex. Non-loopback extraction providers require `https://`; provider credentials and the Owner token are referenced by environment variable name, never command-line value. | the confirm invocation plus the explicit Owner URL; provider is **local Ollama by default** (`http://127.0.0.1:11434/v1`); any OpenAI-compatible endpoint requires explicit `--base-url/--model` |
| Cleanup | `SessionEnd` → `prune_scratch.py` (≤3 s) | expires unpaired pairing scratch (48 h TTL) | none |

Prompt staging is enabled by default. Set `QDRANT_MEMORY_CODEX_AUTO_CAPTURE=0` to
disable it; removing only the `Stop` hook still stages prompt text until TTL
pruning.

Unpaired/interrupted turns are simply not captured (the pairing scratch is
keyed by session+turn, with a session-level fallback when the client omits
`turn_id` on `UserPromptSubmit`). Re-running a Stop for the same turn
overwrites its own event (idempotence, including at ring capacity). Failures
never block the turn: capture failures emit one content-free `systemMessage`
diagnostic; extraction failures keep the event `pending` with a recorded
`last_error` for the next run. Unreadable pending files are quarantined as
`*.corrupt` (reported by the extractor) instead of silently consuming ring
capacity.

`Stop`-based **extraction** (an automatic LLM call inside the session)
is still not part of the hooks: extraction is the operator's explicit command
so that its consent, provider and budget decisions are visible. With the
released Runtime 0.6.1, the optional Owner path submits validated candidates
to `qdrant-memory/extraction-v1`; the Owner performs scope checks, relation
review and durable idempotent writes. The local `add` path remains available
for a standalone Codex profile.

## Privacy and retention facts

- Snapshots stay on this machine under the configured profile
  (`events/codex/`); 0600 files, 0700 directories; nothing is transmitted
  except what the extraction provider receives during the operator's explicit
  `confirm` run (local Ollama by default).
- `codex-plugin remove` (the preview plugin) and `uninstall` never delete the
  profile, staged events, extracted events, or stored memories.
- Purge paths: delete `profile/events/codex/` (aborts staged content before
  extraction) — and, when `PLUGIN_DATA` is set for the hooks, also
  `$PLUGIN_DATA/turn_inputs/` (the pairing scratch lives there instead of the
  profile) — or use Runtime-scoped deletion for stored memories. Extraction
  decisions (admitted / skipped / refused reasons, replacement outcomes) are
  recorded in each event's file.
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
# plan only (default; zero writes; loopback providers only):
python3 integrations/codex-lifecycle/plugin/hooks/extract_pending.py \
  --model qwen3:4b --limit 25
# admit facts through the local Runtime:
python3 integrations/codex-lifecycle/plugin/hooks/extract_pending.py \
  --model <model> --confirm
# alternatively, opt in to the protected HTTPS Owner; only candidates are sent:
python3 integrations/codex-lifecycle/plugin/hooks/extract_pending.py \
  --model <model> --confirm \
  --owner-lifecycle-url https://<owner-host> \
  --owner-token-env QDRANT_MEMORY_REMOTE_TOKEN
```

The Owner route requires a Runtime 0.6.1+ CLI, an explicitly enabled and
authorized Owner lifecycle grant, and a token injected into the Runtime
process environment. The `--owner-token-env` argument is an environment
variable name, never the token. An optional `--owner-ca-file` selects a custom
CA bundle. Owner requests use Runtime's `remote-event` command and its
protected TLS client; retries inspect the event and retry only its immutable
Owner plan. Failed and quarantined events stay pending and require explicit
Runtime operator recovery before the adapter retries them. This route has unit
and local synthetic coverage; an authenticated real Owner endpoint has not been
verified in this environment.

Ollama must already serve the chosen chat model locally; the OpenAI-compatible
client calls `POST {base_url}/chat/completions` with `temperature 0` and a
strict JSON contract, and refuses empty/oversized/secret-shaped candidates.
The example model must support chat completions (embedding-only models such as
`qwen3-embedding:*` cannot answer the extraction prompt).

> **Codex CLI 0.165.0 observation (2026-11-11):** marketplace installation
> succeeds and the installed cache contains `plugin.json`, `hooks/hooks.json`,
> and all four hook scripts. In two isolated CLI sessions, `/hooks` reported
> zero installed and zero active handlers for `SessionStart`,
> `UserPromptSubmit`, `Stop`, and `SessionEnd`: once in embedded Ollama mode
> (`--oss`) and once in the normal shared-server mode with the built-in
> `ollama` provider. No lifecycle hook fired. This confirms a registration
> failure for the tested CLI version; it does not establish Codex Desktop
> behavior. Keep this preview experimental until the Desktop GUI shows the
> hooks, the user reviews and trusts them, and synthetic-session events fire.

## Verification status (2026-11-11)

| Check | Result |
|---|---|
| Handler units: scratch staging, pairing, byte caps, deterministic event IDs, idempotent overwrite, overflow marker, PLUGIN_DATA precedence, no-Runtime-invocation by capture, TTL prune, extraction validation (extra keys, secret-shaped, oversized, importance range), dry-run immutability, dedupe skip, failure keeps `pending` with recorded error | **PASS** (`tests/test_codex_lifecycle_hooks.py`, macOS arm64) |
| Real-Runtime round trip: Stop capture → stub extractor → `--confirm` → real Runtime `add` in the shared profile → Runtime `search` finds the record → pending emptied | **PASS** (`tests/test_codex_capture_integration.py`) |
| Repository marketplace accepts the hooks plugin manifest from the real Codex CLI 0.165.0 (`plugin add`/`mcp list`/`remove`) | **PASS** (per the readiness branch evidence; hooks cache resolution verified) |
| Codex CLI 0.165.0 hook registration in isolated embedded and normal-server sessions | **FAIL** — `/hooks` showed 0 installed / 0 active for all four events; see caveat |
| A real trust-reviewed Codex Desktop session firing all four hooks | **NOT VERIFIED** — Desktop GUI review is pending; do not treat this preview as verified until then |
| Synthetic extraction quality with a real local model | **PASS** — Ollama `qwen3:8b`, 5/5 synthetic cases after a prompt refinement; the first pass exposed one-time calculation leakage, which the refined prompt filtered |
| `Stop`-based in-session extraction (Route A) | **NOT IMPLEMENTED** by design (see pipeline note) |
| Public-directory eligibility of this directory | **NOT APPLICABLE** — hooks are ineligible for public submission per official docs |
