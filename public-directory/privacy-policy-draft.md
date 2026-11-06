# Privacy policy draft — Qdrant Memory for Codex

**Status: DRAFT — not a published policy and not a legal determination. No
public URL exists for this document.** Confirm the publisher identity, contact,
retention and submission-specific legal requirements before publishing it.

## Data handled

The plugin stores only facts the user explicitly asks it to save, plus fields
needed for search, scope, timestamps and recovery. User data remains in the
configured Qdrant collection, local Profile and Runtime ledger. A user may
choose a local embedded Qdrant store, Qdrant Server, Qdrant Cloud or an
authorized Shared Owner.

Codex v1/v2 migration reads the selected native-memory source files. It does
not write to Codex's generated database. Dry-run is intended to report changes
without writing. JSON and Markdown exports can contain private facts and are
written to the user-selected destination.

## Network access

- The default design uses local Qdrant and CPU embeddings.
- If the user chooses CPU model preparation, the Runtime downloads the pinned
  model artifacts from the recorded Hugging Face/Qdrant repository revision,
  checks exact size and SHA-256, and publishes a complete cache atomically.
- Qdrant Cloud is accessed only when the user configures a Cloud endpoint.
- Ollama or an OpenAI-compatible embedding endpoint is accessed only when the
  user explicitly configures that provider. A configured provider receives the
  memory text and search queries that need embeddings; that content leaves the
  user's machine.
- The plugin does not silently fall back from local CPU to a cloud embedding
  service.
- This source candidate declares no telemetry or automatic conversation
  capture. The final Desktop archive has not yet received a complete network
  and dependency audit.

## Credentials

Qdrant and embedding credentials are user-supplied configuration. The plugin
must not read Codex private login credentials. Secrets must not be stored in the
plugin ZIP, command arguments, sample logs or exported build metadata. Creator
normalization and final Desktop process-environment forwarding remain
unverified.

## Retention and deletion

The user controls Qdrant retention and may delete specific memories by exact ID.
Uninstalling the plugin is designed to leave Qdrant data, Profiles, model cache
and exported files intact. The exact Desktop-only package has not yet completed
upgrade/uninstall testing.

## Contact

Publisher and privacy contact: **DRAFT — confirm a monitored public address**.
Current public support issue tracker:
https://github.com/cnkang/qdrant-memory-mcp/issues
