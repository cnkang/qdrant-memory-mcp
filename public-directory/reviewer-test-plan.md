# Reviewer test plan

Status: prepared for a later review; **not executed against a Creator-normalized
Desktop-only package**. Candidate and platform fields must be filled using the
exact final ZIP SHA. The five positive and three negative cases below are
acceptance scenarios, not results.

## Positive cases

| ID | Prompt and synthetic data | Expected actions | Actual result / artifact / pass |
|---|---|---|---|
| P1: New local setup | “Set up a new isolated local Qdrant Memory profile using CPU embeddings. Explain the model download and wait for my choice before preparing it.” Synthetic user scope `reviewer-local`, memory `prefers concise incident summaries`. | Discover Setup Skill; create or connect an isolated profile using the existing supported setup path; explicit consent before model preparation; then `qdrant_memory_add` and `qdrant_memory_search`. No maintenance MCP tool. | **NOT RUN** on Desktop. Existing Runtime model and local setup tests are not proof of GUI success. Artifact: none. Pass: NOT RUN. |
| P2: Save and retrieve | “Remember that the demo project uses a synthetic blue-green deployment. Find it when I ask about the demo deployment.” | One `qdrant_memory_add`, then `qdrant_memory_search`; exact text and scope are confirmed. | `tests/test_codex_plugin.py::test_node_entrypoint_real_mcp` and full file run: **20 passed in 2.34s**, with MCP SDK 2.3.0 and synthetic add/search. Desktop candidate: **NOT RUN**. Artifact: local pytest output. Pass: source MCP only. |
| P3: Exact-ID update | “Update memory `<captured-id>` to say the synthetic deployment uses a 10-minute observation window.” | `qdrant_memory_update` with exactly the returned ID and replacement text; search confirms only that ID changed. | Existing `docs/codex-plugin-verification.md` records Codex CLI update acceptance for 0.1.2. Re-run against exact ZIP required. Desktop candidate: **NOT RUN**. Artifact: historical verification record. Pass: NOT VERIFIED for Desktop package. |
| P4: Exact-ID delete | “Delete only memory `<captured-id>`.” | `qdrant_memory_delete` using the exact returned ID; confirm that ID is absent and a neighboring synthetic record remains. | Existing `docs/codex-plugin-verification.md` records Codex CLI delete acceptance for 0.1.2. Re-run against exact ZIP required. Desktop candidate: **NOT RUN**. Artifact: historical verification record. Pass: NOT VERIFIED for Desktop package. |
| P5: Native-memory import and portable export | “Dry-run import these synthetic Codex v1 and v2 fixtures, show duplicates and skipped sensitive records, then export the approved records to JSON and Markdown.” Fixtures: one unique v1 fact, one unique v2 fact, one duplicate, one synthetic secret-like string. | Setup/migration Skill; inspect v1 and v2 sources; dry-run with zero writes; user approval; import; export and verify file and record hashes. Report `HANDOFF_PENDING`, never native adoption. | Focused Runtime migration suite: **14 passed, 54 deselected** for dry-run zero writes, resume/export, v1/v2 layouts, de-duplication, sensitive content, unsafe paths and handoff checksums. This Desktop package run: **NOT RUN**. Artifact: local Runtime pytest output, no exact ZIP artifact. Pass: Runtime source tests only. |

## Negative cases

| ID | Prompt and synthetic data | Expected actions and result | Actual result / artifact / pass |
|---|---|---|---|
| N1: Unauthorized scope or ID | “Delete ID `<ID from another test scope>` and search as `other-user`.” | No cross-scope read or mutation. Exact-ID lookup fails without exposing the other scope's text. | Runtime has scoped exact-ID checks; current candidate Desktop/MCP negative invocation: **NOT RUN**. Artifact: none. Pass: NOT RUN. |
| N2: Incompatible embedding fingerprint | Configure a disposable test collection with fingerprint A, then request a write with incompatible fingerprint B. | Reject before Qdrant/ledger mutation; no implicit re-embedding, collection rebuild or provider fallback. | Runtime fingerprint tests exist; exact candidate negative run and zero-write evidence: **NOT RUN**. Artifact: none. Pass: NOT RUN. |
| N3: Unsafe path or suspected sensitive source | Ask to import a source containing a symlink/reparse escape and a synthetic API-key-shaped value. | Refuse unsafe path; skip sensitive content; no file outside the selected source is read or modified; report sanitized reason. | Runtime/package source checks exist. Windows reparse-point test and exact package run: **NOT RUN**. Artifact: none. Pass: NOT RUN. |

## Evidence record fields

For every execution, record plugin version, exact ZIP SHA-256, source commit,
Runtime/MCP/Skill versions, operating system and architecture, Codex Desktop
version, MCP protocol/client version, command or user-visible steps, tool calls,
sanitized result, artifact link and `PASS` / `FAIL` / `NOT RUN`. Do not record
real user memories, API keys, access tokens or private Qdrant credentials.
