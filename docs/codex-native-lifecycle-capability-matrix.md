# Codex native lifecycle capability matrix (2026-11-09)

A short capability comparison between the DSH native work (PR #81,
`codex/dsh-native-v1`, Cordis adapter) and what the **official** Codex plugin
contract offers. Everything below the research row is verified from the pages
quoted; anything unverified is labeled.

## Official Codex plugin capabilities (verified from released docs)

Sources: [Build plugins](https://developers.openai.com/plugins/build/plugins),
\(Hooks)[https://learn.chatgpt.com/docs/hooks],
[Submission](https://developers.openai.com/plugins/deploy/submission),
[Desktop-only](https://developers.openai.com/plugins/deploy/desktop-only).

| Capability | Official support | Exact basis |
|---|---|---|
| Turn-start capture (`UserPromptSubmit`) | Yes, plain text `prompt` in hook input; `matcher` unused for this event | Hooks reference: "`prompt` \| User prompt that's about to be sent" |
| Recall/context injection | Yes: `hookSpecificOutput.additionalContext` on `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PreToolUse`; plain text on `stdout` for `SessionStart` adds developer context | Hooks reference: "That `additionalContext` text is added as extra developer context" |
| Turn completion (`Stop`) | Yes, public event with `last_assistant_message`, `turn_id`, `stop_hook_active`; `decision: block` creates a continuation prompt | Hooks reference: Stop section |
| Session resume/restore detection | Yes: `SessionStart` matcher `startup\|resume\|clear\|compact\|fork` | Hooks reference: source values |
| Session end | Yes: `SessionEnd` (advisory, synchronous, 1 s default timeout) | Hooks reference |
| Fork / subagent semantics | Yes: `SubagentStart`/`SubagentStop`/`SubagentStop` input fields, `source: "fork"` | Hooks reference |
| Reading chat logs directly | Not a stable interface: "`transcript_path` points to a chat transcript for convenience, but the transcript format isn't a stable interface for hooks" | Hooks reference |
| Native memory read/write API for plugins | **No public API found.** The words "memory"/"memories" do not appear in the plugin/MCP packaging pages; Codex memories (`features.memories`, `memories_v2/`) document no plugin access | Full-page scans, 2026-11-09 |
| Trust boundary | Plugin-bundled hooks are non-managed, skipped until reviewed/trusted per definition hash; `/hooks` (CLI) or Settings→Hooks (Desktop); feature flag `[features].hooks=false` | Build plugins + hooks reference |
| Public directory eligibility | **Denied**: "Plugins containing lifecycle hooks aren't eligible for the public plugin directory"; "Remove lifecycle hooks before public directory submission" | Build plugins; Submission |
| Manual install (desktop) | Explicitly allowed: "Lifecycle hooks are supported for plugins installed manually in Codex desktop" | Build plugins |

## DSH native parity points and their Codex translations

| DSH capability (PR #81 scope) | Codex official equivalent | Status in this repo |
|---|---|---|
| Automatic memory extraction from turn content | `Stop` hook receives `last_assistant_message`, but semantic extraction needs a designated model, consent flow and processing disclosure. No official extraction service is exposed to plugins. | **Not implemented** by design (`integrations/codex-lifecycle` README); heuristics would fake semantics |
| Automatic recall on session start / prompt | `SessionStart` + `UserPromptSubmit` `additionalContext` | **Implemented (experimental)**: `session_recall.py` |
| Durable receipts / session resume | Hook events don't expose durable receipt storage; `PLUGIN_DATA` is a writable plugin data directory | Not needed for the explicit tools; Runtime ledger remains the receipt store |
| Fork/subagent isolation | Hook input distinguishes subagent events (`SubagentStart`/`Stop`); a fork recursion risk exists; not addressed in this preview | Documented as a known limitation, not silently built |
| Native memory import | CLI-only official `codex` interfaces; plugin route is Runtime's read-only v1/v2 adapter (existing) | Existing (Migration skill) |
| Session recovery without reading logs | Hooks deliver official event payloads, so capture/injection never needs rollout files | Enforced in hook code (no `transcript_path` reads) |

## Reuse boundary with the shared Runtime

The hooks call the **same** Python Runtime CLI and the **same** profile as the
portable plugin (`QDRANT_MEMORY_CODEX_*` overrides match the launcher's). No
second collection, second ledger, second WriterLease or second embedding
pipeline is created, and Codex native memories are left untouched. Automatic
semantic extraction remains **NOT IMPLEMENTED** and requires an explicit
product decision (extraction model, consent, disclosure, duplication policy)
before any `Stop` hook is added.
