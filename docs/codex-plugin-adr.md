# ADR: portable Codex plugin over one memory Runtime

Date: 2026-11-03. Status: implementation candidate, public release gated.

## Update 2026-11-09: verified spec deltas and Mode B separation

Released-spec verification changed three recorded claims:

1. **Hooks are officially documented for plugins.** `extensions.com.openai`
   gains a `hooks` mapping (path, path list, or inline object) loading
   `hooks/hooks.json` by default; events `SessionStart` (with
   `startup|resume|clear|compact|fork` source matching), `UserPromptSubmit`,
   `Stop` (turn completion, `last_assistant_message`), `SessionEnd`,
   `PreToolUse`/`PostToolUse` and others are public per the released hooks
   reference. Hooks load only for manually installed Codex desktop plugins,
   are skipped until trust-checked per definition hash, and are barred from
   public-directory submission. Decision unchanged, now sharpened: **the
   public-ready portable package carries no hooks** (asserted by tests), and
   lifecycle experiments live only in
   `integrations/codex-lifecycle/` as a separate manual-install preview that
   reuses the single Runtime profile. Automatic turn extraction stays
   unimplemented (no official extraction service; heuristics are forbidden).
   [Build plugins](https://developers.openai.com/plugins/build/plugins),
   [Submission](https://developers.openai.com/plugins/deploy/submission),
   [Hooks](https://learn.chatgpt.com/docs/hooks).

2. **The portable MCP schema has no `env_vars`.** The released 1.0.0 schema
   allows `type|command|args|cwd|env` only. The Codex overlay `env_vars`
   remains a Codex-specific passthrough, validated by the real CLI surfacing
   all eight names with masked values. Creator-side normalization for a
   portable upload derives `.mcp.json`/`.codex-plugin/plugin.json` from the
   root manifests; whether the eight names survive that derivation for this
   candidate is NOT VERIFIED and stays a blocker for the Creator copy.

3. **Per-platform packaging remains open.** The released MCP schema still has
   no OS/arch field and the desktop-only page still documents a single stdio
   command plus "the server and its dependencies"; only hook handlers have
   `commandWindows`. A universal ZIP therefore needs a dispatcher whose Node
   availability on a clean desktop install is unverified. Meanwhile the
   dependency payload now has a real prototype:
   `runtime-locks/*.txt` (hash-locked per-platform transitive resolutions)
   plus the pinned-commit Runtime wheel SHA-256, with `--require-hashes`
   offline installs verified on macOS arm64; macOS x64 remains **NOT VERIFIED**.
   NO-GO is unchanged: no
   bundle layout, SBOM, license aggregation or desktop launch route exists.

## Decision

One Memory. Multiple Agents. No Lock-in. Readable exports, documented import
adapters, source provenance and a safe exit are core requirements. Prefer any
harness's supported import/export API when it exists. Never imply support for
all native formats or write APIs without evidence. Runtime's existing JSON is
the interoperability floor; Codex adds a checksummed JSON/Markdown handoff.

Use a root Agent Plugins 1.0 `plugin.json`, fixed-location `mcp.json`, four skill
directories and a repository `.agents/plugins/marketplace.json`. No divergent
legacy MCP files or hooks. A synchronized `.codex-plugin/plugin.json` overlay
adds Codex's supported `env_vars` allowlist; source inspection and real-client
testing confirmed Codex otherwise drops optional profile paths and credentials.
Validation requires identical identity, onboarding and stdio command in both
formats, so the overlay cannot select a different backend.
`extensions.com.openai.onboardingSkill` points at setup.
Portable plugin identity/version is independent of MCP and Runtime versions.

The plugin boundary is a small dependency-free Node ESM process that starts the
existing Python MCP Runtime over stdio. Node 20+ and Python 3.11+ are explicit
requirements. Official packaging docs define a language-neutral executable
contract; they do not mandate that a local MCP use Node or TypeScript. Node at
the host boundary is our engineering choice, not an invented OpenAI requirement.
See [packaging](https://developers.openai.com/plugins/build/plugins) and
[local MCP](https://developers.openai.com/plugins/build/mcp-server).

The existing managed launcher was evaluated. Its released Runtime/dependency
snapshot and WorkBuddy auto-setup semantics must not silently become this new
plugin's defaults. Codex uses a thin stdio launcher with explicit setup and an
immutable Runtime source pin. Existing WorkBuddy/DSH packages are unchanged.
No second JSON-RPC implementation, embedding engine, collection schema or ledger.

Reusable native artifact parsing lives in the Runtime migration adapter. CLI
orchestration reuses Runtime scope, lease, collection identity and migration
manifests. General guidance is bundled from an exact cnkang/skills Git snapshot
at archive build; the source wrapper is intentionally small. No perpetual fork.

## Native guarantees

Official [memory documentation](https://developers.openai.com/codex/memories)
and openai/codex main `616cab3a3529f572c3385098c12698278770ea98` were inspected.
v1's MEMORY.md registry (summary fallback) and v2's consolidated memory_summary.md
are separate layouts. Supporting rollout/raw evidence is excluded by default.
TOML configuration is advisory evidence; effective Desktop/CLI/IDE overrides and
per-chat memory mode require client verification. Missing flags report UNKNOWN.

No stable public plugin bulk-native-write API was verified. Internal ad-hoc note
implementation is not such an API. Exit exports remain HANDOFF_PENDING. Users
review facts, enable native memory, request approved saves through their actual
client and verify adoption in a fresh chat. Generated Markdown is not native
import; AGENTS.md is project instruction and requires separate authorization.

## Embedding and shared ownership

Local CPU is the setup default, using Runtime FastEmbed 0.9.1 and its pinned
384-dimensional multilingual model. Model download is explicit; missing models
cannot trigger cloud fallback. Ollama and OpenAI-compatible services require
explicit selection. No Codex credential inheritance or native embedding API is
assumed. Runtime fingerprints include model/provider/dimension/distance,
instructions, normalization and pipeline identity. Incompatible provider changes
require a new collection, re-embedding, verification and approved client switch.

Private Codex profiles are isolated. Existing concurrent agents use the existing
Shared Owner credential-bound bridge; the launcher never opens a parallel ledger
in shared mode. Protected bulk migration is not bypassed; offline operator
portability remains subject to the Runtime destination enrollment boundary.

## Release constraints

This paragraph records the inventory when the ADR was drafted: Runtime Issue
#115 remained open, PRs #116 and #117 were under review, and the latest public
Runtime/MCP versions were 0.5.5/0.2.9. That status is historical. Runtime 0.6.0
is now public, and this release candidate pins its immutable main commit; see
`runtime-source.json` and `docs/publishing.md` for the current pin and release
sequence. Transitive resolver installs are not equivalent to a fully
hash-locked desktop-only runtime bundle.

P1 automatic capture remains deferred, off by default. It requires independent
consent, exclusions, processing disclosure and duplicate-injection analysis.
Public-directory packages exclude hooks. Local MCP public submissions currently
require approved-partner allowlisting and a verified developer identity:
[desktop-only submission](https://developers.openai.com/plugins/deploy/desktop-only).
Technical readiness must never be called official approval.
