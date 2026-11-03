---
name: memory-migration
description: Preview and import authorized Codex native v1/v2 semantic memories through the existing Runtime migration ledger.
---

# Import native Codex memory

Check `qdrant-memory --home PROFILE codex --help`. Use the pinned Runtime.
Select an explicitly approved canonical Codex home and fixed profile scope.
Run `qdrant-memory --home PROFILE codex inspect --codex-home HOME`, then
`qdrant-memory --home PROFILE codex migrate --codex-home HOME
--dry-run`. Inspect the local source preview, skipped records, fingerprints and
target IDs. Never read credentials, raw chat logs or unrelated agent scopes.

v1 reads MEMORY.md (summary fallback); v2 reads consolidated memory_summary.md.
Unknown formats fail or report EMPTY_OR_UNKNOWN_LAYOUT. Duplicates preserve source
mappings. Select a source version with `--source-version` and exact topic/category
headings with repeated `--heading` options. Project-named sections can be selected
this way, but source text never controls the authorized destination scope.
Sensitive patterns and code blocks are skipped, but manual review is
still required for personal information. Large CPU inputs fail explicitly.

Only after approval run
`qdrant-memory --home PROFILE codex migrate --codex-home HOME --confirm --verify`.
Resume interruption with `--confirm --resume --retry-failed --verify` using the
same source snapshot. The Runtime uses its existing ledger and lease. Never
reset a collection, change scope or bypass a protected Shared Owner policy.

For other harnesses prefer documented adapters and standard Runtime JSON import.
Do not invent native APIs or treat internal DB/file writes as supported imports.
Source native files remain intact. Native writeback is not supported; use the
memory-backup handoff workflow and keep HANDOFF_PENDING until actual adoption.
