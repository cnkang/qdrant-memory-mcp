---
name: memory-backup
description: Export and verify portable Qdrant JSON/Markdown, safely exit the plugin and guide a pending Codex native handoff.
---

# Backup, exit and rollback

Use `qdrant-memory --home PROFILE codex export --output ./NEW_DIRECTORY --confirm`
only after approval for that exact scope and destination. Then run `qdrant-memory
codex verify --output ./NEW_DIRECTORY`. Exports contain readable JSON and Markdown,
provenance, timestamps and SHA-256 checksums. No plugin or service is needed to
read them. Keep the original collection, ledger and source memories.

Report HANDOFF_PENDING, never NATIVE_VERIFIED. Ask the user to review the exported
facts and use the installed Codex client's supported remember interaction for
approved items. Explain any model/cloud processing path before sending private
data. Enable native memories and verify actual adoption in a fresh chat. Do not
edit generated native files or internal SQLite. AGENTS.md needs separate approval
and is project instruction, not native import. There is no verified public bulk
native-write API in this release.

After review, disable the plugin through Codex settings. `codex plugin remove
qdrant-memory@cnkang` uninstalls its cache. Neither operation may delete
Qdrant storage, native memory or export files. Reinstall the same pinned version
to roll back; keep the old profile and embedding identity. Delete backups or
collections only under a separate explicit deletion request.
