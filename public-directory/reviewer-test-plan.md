# Reviewer test plan

Status: prepared for a later review; **not executed against a Creator-normalized
Desktop-only package**. Candidate and platform fields must be filled using the
exact final ZIP SHA. The five positive and three negative cases below are
acceptance scenarios, not results.

## Positive cases

| ID | Prompt and synthetic data | Expected actions | Actual result / artifact / pass |
|---|---|---|---|
| P1: New local setup | “Set up a new isolated local Qdrant Memory profile using CPU embeddings. Explain the model download and wait for my choice before preparing it. After setup, ask separately before saving this synthetic memory: `prefers concise incident summaries`.” Synthetic user scope `reviewer-local`. | Discover Setup Skill; create or connect an isolated profile using the existing supported setup path; obtain explicit consent before model preparation and separate explicit approval before saving the synthetic memory. Do not call `qdrant_memory_add` or search before that approval. After approval, call `qdrant_memory_add`, then `qdrant_memory_search` to confirm it. No maintenance MCP tool. | **NOT RUN** on Desktop. Existing Runtime model and local setup tests are not proof of GUI success. Artifact: none. Pass: NOT RUN. |
| P2: Save and retrieve | “Remember that the demo project uses a synthetic blue-green deployment. Find it when I ask about the demo deployment.” | One `qdrant_memory_add`, then `qdrant_memory_search`; exact text and scope are confirmed. | `tests/test_codex_plugin.py::test_node_entrypoint_real_mcp` and full file run: **20 passed in 2.34s**, with MCP SDK 2.3.0 and synthetic add/search. Desktop candidate: **NOT RUN**. Artifact: local pytest output. Pass: source MCP only. |
| P3: Exact-ID update | “Update memory `<captured-id>` to say the synthetic deployment uses a 10-minute observation window.” | `qdrant_memory_update` with exactly the returned ID and replacement text; search confirms only that ID changed. | Existing `docs/codex-plugin-verification.md` records Codex CLI update acceptance for 0.1.2. Re-run against exact ZIP required. Desktop candidate: **NOT RUN**. Artifact: historical verification record. Pass: NOT VERIFIED for Desktop package. |
| P4: Exact-ID delete | “Delete only memory `<captured-id>`.” | `qdrant_memory_delete` using the exact returned ID; confirm that ID is absent and a neighboring synthetic record remains. | Existing `docs/codex-plugin-verification.md` records Codex CLI delete acceptance for 0.1.2. Re-run against exact ZIP required. Desktop candidate: **NOT RUN**. Artifact: historical verification record. Pass: NOT VERIFIED for Desktop package. |
| P5: Native-memory import and portable export | “In a new disposable Codex profile, dry-run import these synthetic v1/v2 fixtures, show duplicates and skipped sensitive records, then ask before exporting the complete target scope to JSON and Markdown.” Fixtures: one unique v1 fact, one unique v2 fact, one duplicate, one synthetic secret-like string; no earlier profile memories. | Create a fresh profile and empty target scope; verify the baseline is empty. Inspect v1/v2 sources; dry-run with zero writes; obtain user approval; import. Verify the exact complete scope record set, disclose that `codex export` exports the whole scope, and obtain approval before export. Verify both the exported record set and file/record hashes. Report `HANDOFF_PENDING`, never native adoption. | Runtime source run at commit `4ca2950f0bfac20cd7e10081320c207b90fdbc16`: filtered `tests/test_codex_memory.py` returned **64 passed, 4 deselected** (the four deselected CLI/profile cases need the Hermes host `utils` module); it covers dry-run zero writes, resume/export, v1/v2 layouts, de-duplication, sensitive content, unsafe paths and handoff checksums. This Desktop package case: **NOT RUN**. Artifact: local Runtime pytest output, no exact ZIP artifact. Pass: Runtime source tests only. |

## Negative cases

| ID | Prompt and synthetic data | Expected actions and result | Actual result / artifact / pass |
|---|---|---|---|
| N1a: Agent refusal for foreign scope | “Delete ID `<synthetic ID from another test scope>`.” | Record agent refusal as an authorization result; verify `qdrant_memory_delete` is not invoked and no foreign-scope content is disclosed. This does not count as Runtime scope-enforcement evidence. | **NOT RUN** on Desktop. Artifact: none. Pass: NOT RUN. |
| N1b: Runtime rejects direct foreign-ID delete | Directly invoke `qdrant_memory_delete` with a synthetic record ID created in scope `alice` while the tool request is authorized as scope `bob`. | The direct tool call fails with a scope error and does not reveal the record; verify the original record remains unchanged. Keep this separate from the agent-refusal case. | Runtime source test `tests/test_store_runtime.py::test_scope_isolation_and_wrong_scope_tool_delete` covers this contract. Exact candidate Desktop/MCP invocation: **NOT RUN**. Artifact: none. Pass: Runtime source only. |
| N2: Incompatible embedding fingerprint | Configure a disposable test collection with fingerprint A, then request a write with incompatible fingerprint B. | Reject before Qdrant/ledger mutation; no implicit re-embedding, collection rebuild or provider fallback. | Runtime fingerprint tests exist; exact candidate negative run and zero-write evidence: **NOT RUN**. Artifact: none. Pass: NOT RUN. |
| N3a: Unsafe source path | Import a synthetic Codex source whose recognized `MEMORY.md` path is a symlink to a file outside the selected profile. Do not place a secret-like value in this fixture. | Refuse during source inspection before record classification; do not import or expose outside-path content. | Runtime source test `tests/test_codex_memory.py::test_symlink_and_malformed_rejected` covers symlink refusal. Windows reparse-point and exact package cases: **NOT RUN**. Artifact: none. Pass: Runtime source only. |
| N3b: Sensitive content in a safe source | Import a regular, contained `MEMORY.md` with a synthetic API-key-shaped value. | Allow safe-path inspection, skip the sensitive section, and verify no content from that section is imported. | Runtime source test `tests/test_codex_memory.py::test_sensitive_code_unknown_and_empty` covers sensitive-section skipping. Exact candidate Desktop case: **NOT RUN**. Artifact: none. Pass: Runtime source only. |

## Evidence record fields

For every execution, record plugin version, exact ZIP SHA-256, source commit,
Runtime/MCP/Skill versions, operating system and architecture, Codex Desktop
version, MCP protocol/client version, command or user-visible steps, tool calls,
sanitized result, artifact link and `PASS` / `FAIL` / `NOT RUN`. Do not record
real user memories, API keys, access tokens or private Qdrant credentials.
