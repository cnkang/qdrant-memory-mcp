# Codex portability

Codex native v1/v2 inspection, migration and handoff require Runtime 0.6.0 or
later. Discover the actual installed `qdrant-memory codex --help` before use;
the reference alone does not install or upgrade the backend. Keep the Runtime
as the sole storage engine.

## Owner extraction candidate events

Runtime 0.6.1 supports the versioned `qdrant-memory/extraction-v1` input for
authenticated Owner lifecycle events. When a Codex adapter has been separately
authorized and verified, it can submit bounded extracted candidates through
the Owner instead of sending a raw turn. Check the installed
`qdrant-memory remote-event --help` and [Universal Owner](universal-owner.md)
for the exact contract. Candidate text and model output do not grant identity,
scope or write authority. This Skill does not install a Codex hook adapter,
enable automatic capture, or establish Codex host acceptance. Do not send
transcripts or candidates to a remote model without explicit authorization.

Runtime 0.6.2 can retry a persisted `FAILED` Owner event by its existing receipt
after an authorized operator fixes the cause. This Runtime recovery does not
install, enable or authorize Codex capture, and it never retries a
`QUARANTINED` event automatically. Inspect the installed
`qdrant-memory remote-event --help` before using the operation.

Use an explicitly authorized canonical `--codex-home` (or CODEX_HOME). Inspect
both v1 and v2 without reading chats, raw memories, credentials or unrelated
agent data. Configuration inspection cannot prove effective client settings.
Read the source preview locally and run `codex migrate --dry-run` before the
operator approves `--confirm --verify`. Resume with `--resume --retry-failed`.
Do not bypass WriterLease or protected Shared Owner enrollment. A second ledger
must never concurrently write the same collection.

Use `codex export --output ./new-handoff --confirm` for a scoped JSON/Markdown
bundle, then `codex verify --output ./new-handoff`. Keep the original store.
Report HANDOFF_PENDING until adoption is confirmed in the actual native client.
Ask the user to review facts, enable native memory and explicitly ask Codex to
remember approved items. Verify in a fresh chat. Do not edit generated memory
files or internal databases; AGENTS.md is not native memory. Never copy private
content into a cloud processing path without authorization.

There is no verified stable plugin bulk-write API for Codex native memory.
Internal note backends do not establish such a public contract. Preserve this
limitation when describing reversibility. Users retain readable, checksummed
data even when a harness cannot automatically ingest it.

## File and platform boundaries

macOS and Linux use descriptor-anchored no-follow traversal. Windows uses the
Runtime's pywin32 backend and handle-relative traversal on supported local
volumes. Windows native import and handoff verification are covered by dedicated
Runtime CI; they are no longer categorically disabled. All platforms reject
unsafe links, changed paths and unsupported filesystem guarantees. Windows
additionally rejects remote volumes, reparse points and unsafe ACLs. Choose a
private local directory; do not weaken these checks to accept a shared path.

Handoff verification checks bounded files, checksums and record fidelity. It
does not prove that native Codex memory adopted them. Leave `native_verified`
false and report HANDOFF_PENDING until the actual client confirms adoption.
