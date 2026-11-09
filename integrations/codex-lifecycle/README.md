# Qdrant Memory lifecycle experiment (Mode B) — hooks preview

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
public-directory eligibility; a repository test asserts the published package
stays hook-free.

## What it does today (validated only as described below)

| Hook | Event | Behavior contract |
|---|---|---|
| `session_recall.py` | `SessionStart` (`startup\|resume\|clear\|compact\|fork`) | Searches the operator's own Runtime profile with the session working directory name and returns records via the released `hookSpecificOutput.additionalContext` shape. Silent (exit 0, no output) when nothing durable matches. |
| `user_prompt_capture.py` | `UserPromptSubmit` | When the user's prompt begins with `remember:` (case-insensitive, first line), the exact remainder of that line (≤512 chars) is saved verbatim with Runtime `add`. Everything else exits silently. No model call, no extraction, no summarization. |

Automatic turn-completion capture (`Stop`, `last_assistant_message`) is
**deliberately not implemented**: correct semantic extraction requires a
designated extraction model and consent, consent, processing-disclosure and
duplication design that this preview does not ship. Fabricating that with
heuristics would violate the release boundary, so no `Stop` hook exists here.

## Boundaries

- Uses only documented hook inputs and outputs; never reads transcripts,
  rollout files, SQLite, or internal files.
- Every memory operation goes through the existing Python Runtime CLI
  (`bin/qdrant-memory`), so schema, WriterLease, scope and ledger semantics are
  the single Runtime's. Codex native memories are untouched.
- The scope comes from the private Codex profile (`qdrant-memory.json`);
  incomplete profiles fail closed.
- Hook failures are surfaced as `systemMessage` only; they never block the
  prompt or inject misleading context.
- Codex requires trust review per hook definition (`/hooks`, or **Review
  hooks** in desktop); a plugin update re-arms that review. Users opt in
  explicitly.

## Install (manual, local)

```sh
codex plugin marketplace add <repo>/integrations/codex-lifecycle
codex plugin add qdrant-memory-lifecycle@cnkang-lifecycle-preview
# then open /hooks in the CLI (desktop: Settings → Hooks) and trust the two hooks
```

Requirements: the qdrant-memory Codex plugin (main plugin) installed and set up
(profile at `~/.qdrant-memory/codex/profile` by default; `QDRANT_MEMORY_CODEX_*`
environment overrides as documented in the launcher), plus `python3` on PATH
for the hook commands.

## Verification status (2026-11-09)

| Check | Result |
|---|---|
| Handler units against a stub Runtime (input parsing, directive matching, size limits, scope enforcement, additionalContext contract, error surfacing) | **PASS** (`tests/test_codex_lifecycle_hooks.py`, macOS arm64) |
| Repository marketplace accepts the hooks plugin manifest from the real Codex CLI 0.165.0 (`plugin marketplace add` + `plugin add`) | **PASS** (isolated CODEX_HOME; see docs/codex-plugin-verification.md) |
| `codex plugin remove` leaves stored memory data untouched | **PASS** |
| A real Codex session actually firing the hooks (trust-reviewed, subscription client) | **NOT VERIFIED** — requires a subscribed, hook-enabled Codex desktop/CLI session; do not treat this preview as verified until then |
| Hook behavior in ChatGPT/Codex Desktop app | **NOT VERIFIED** |
| `Stop`-based automatic semantic capture | **NOT IMPLEMENTED** by design (needs an approved extraction model and consent flow) |
| Public-directory eligibility of this directory | **NOT APPLICABLE** — hooks are ineligible for public submission per official docs |

## Packaging note

Codex discovers `hooks/hooks.json` inside the plugin root when the OpenAI
extension (here `extensions.com.openai.hooks`) points at it. This preview ships
the hooks under `plugin/hooks/hooks.json` and registers only this preview
marketplace. It is not part of the `plugins/qdrant-memory` package, the built
source ZIP, or the Desktop-only bundle.
