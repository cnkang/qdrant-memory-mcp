# Manual Desktop acceptance and result record

**Current result: NOT VERIFIED.** The available Mac host was locked when the
Desktop inspection was attempted, so no Codex Desktop or ChatGPT Desktop UI
steps were completed. Codex CLI and MCP SDK evidence is recorded separately and
must not be presented as GUI evidence.

## Maintainer procedure

Use a clean desktop account or a new test user profile. Record the exact ZIP
SHA-256 and do not reuse a profile containing prior Qdrant Memory settings.

1. Install the Desktop-only ZIP through the supported Desktop flow. Confirm the
   plugin identity and Setup Skill appear. Record which executable the host
   tries to launch and whether it is present on a clean account.
2. Choose **New Local Setup**. Confirm the Profile and collection are new and
   isolated. Confirm the flow never offers to rebuild an existing Collection.
3. Select CPU embedding. Before preparation, show the exact model name, pinned
   source, approximately 252.1 MB expected download and explicit confirmation.
   Cancel once and confirm no model transfer starts.
4. With the pinned model already cached, disconnect the test machine from the
   network and start the local server. Confirm MCP initialize and discovery of
   exactly `qdrant_memory_search`, `qdrant_memory_add`,
   `qdrant_memory_update` and `qdrant_memory_delete`; no download occurs.
5. In a disposable local profile, add one synthetic fact, search it, update its
   exact returned ID and delete that exact ID. Verify the neighboring synthetic
   record remains.
6. Restart Codex and repeat search. Confirm the fact persisted in the same
   isolated Profile and no second collection was created.
7. Import synthetic v1/v2 Codex-memory fixtures. Run dry-run first and verify
   zero writes; approve import; export JSON and Markdown; check file and record
   hashes. Confirm export status says `HANDOFF_PENDING` unless Codex adoption is
   independently verified in a fresh chat.
8. Test explicit existing-Qdrant setup only against an authorized disposable
   server. Test a Shared Owner only with an authorized test token. Do not use a
   production collection.
9. Disable the plugin, restart Desktop and verify data remains. Re-enable it,
   then test upgrade and rollback with a backup and the same embedding
   fingerprint. Uninstall and verify Qdrant data, ledger, model cache and
   exported files still exist and remain readable without the plugin.
10. Repeat on Apple Silicon macOS, Intel macOS, Windows x64 and Linux x64 as a
    development compatibility target. Report Codex Desktop support only for
    platforms confirmed by current official docs and actual Desktop execution.

## Required record

| Host / platform | Version and architecture | Install / initialize / tools | CPU offline / first download | Migration / restart | upgrade / uninstall | Result |
|---|---|---|---|---|---|---|
| Codex CLI | 0.165.0, macOS arm64 | Local source Marketplace install and MCP config observed; separate from Desktop | Not a Desktop run | Existing CLI evidence only | Existing CLI evidence only | PASS for CLI source install only |
| Codex Desktop | NOT RECORDED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| ChatGPT Desktop | NOT RECORDED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| macOS Intel | NOT AVAILABLE | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Windows x64 | NOT AVAILABLE | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Linux x64 | Dev target only | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |

## Observed environment blocker

The computer-use session reported no available app surface because the Mac was
locked, and the authorized UI automation did not unlock it. No alternate UI
control was used. Repeat the manual procedure on an available Desktop host.
