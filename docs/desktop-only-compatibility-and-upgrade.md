# Version compatibility and maintainer upgrade checklist

Inventory refreshed 2026-11-06; the Skill, MCP branch and Runtime CI PR are separate
development changes. No host adapter release is synchronized by this task.

## Current version map

| Component | Current candidate pin | Evidence / compatibility boundary |
|---|---|---|
| Plugin | 0.1.3 candidate | Independent plugin version, bumped for the bundled Skill 0.4.1 update. Current GitHub Marketplace package is a lightweight source install. |
| MCP distribution | 0.3.1, tag commit `e106f7de29da1a4ef889ccd589bdc76bb5092d6a` | Metadata/stdio adapter; delegates all memory operations to the Runtime. |
| Runtime | 0.6.0, release commit `dee6777432f17523db75f6be32cf3ef15e48235c` | Authoritative Qdrant, embedding, scope, SQLite ledger, recovery and WriterLease implementation. |
| Skill | 0.4.1 candidate, repository commit `d42985ba9011edc48d7c103f79cf40709fd979e5` | Guided operator workflows added in Skills draft PR #54; the plugin snapshot is refreshed to match all 21 source files. |
| Launcher | Plugin 0.1.3 source | Dependency-free Node ESM host adapter. The Desktop-only ZIP still requires a bundled or confirmed host Node runtime. |
| Python test matrix | 3.11 / 3.14 | Runtime Issue #118 correction is in PR #127; GitHub exact-SHA jobs have not yet completed. |
| Model | FastEmbed 0.9.1; MiniLM-L12-v2, 384 dimensions | 252,138,706 bytes of immutable verified model files. Model cache is separate from plugin code. |

The Skill source change is limited to onboarding instructions; Runtime, tool
schemas and data formats are unchanged. The new operator guide keeps setup,
diagnostics, migration and export in the separately installed Runtime CLI.

## Host boundaries

- Hermes Native Provider, WorkBuddy Connector and DSH Bundle continue using
  their existing Runtime integration contracts.
- OpenCode/Pi use the existing MCP distribution and tool schemas.
- Codex Marketplace remains the source-install target.
- Desktop-only is a separate future archive target; it must reuse the same
  Runtime, schemas, Skills and Profile format.
- Do not alter Qdrant schema, Profile, Ledger or collection identities merely
  to make packaging easier.

## Maintainer upgrade checklist

1. Reconfirm Runtime, MCP and Skill tags/commits from their authoritative
   repositories. Verify pinned Skill bytes against the package snapshot.
2. Inspect the exact Runtime and MCP diff, run their migration, MCP protocol,
   crash/recovery, embedding fingerprint and host compatibility suites.
3. Run every Python matrix cell with the declared interpreter and record
   `sys.executable`, `sys.version`, implementation, `pip`/`uv`, installed
   Runtime distribution and install path. Bind evidence to the exact commit.
4. Resolve Runtime #115 through worker/ledger/lease evidence. Do not increase
   timeouts or add retry loops as a substitute for a root cause.
5. Build the Marketplace source archive with
   `python scripts/build_codex_plugin.py --output <path>` and run
   `--validate`. This target does not produce a Desktop-only package.
6. Build a Desktop candidate only from a clean commit and complete per-platform
   bundles. Verify provenance, wheel hashes, executables, SBOM, licenses,
   archive paths, secret scan, ZIP SHA-256 and exact contents.
7. Install that exact archive on each confirmed Desktop platform. Test CPU
   preparation, four tools, migration, persistence, update, rollback and
   uninstall. Record unexecuted cells as NOT VERIFIED.
8. Confirm Plugin Creator normalization using a supported validation path.
   Preserve portable root manifest authority and verify the environment overlay
   does not widen scope or expose values.
9. Update `release.json`, test matrix, listing drafts and demo evidence. Keep
   the source Marketplace and Desktop-only candidate versions independently
   traceable.
10. Prepare a reviewable PR and internal artifact. Do not merge, tag, publish or
    submit unless separately authorized.

## Rollback

Keep the old plugin version and Runtime environment available. Back up the user
Profile and export JSON/Markdown before any Runtime or embedding-pipeline
upgrade. If an embedding fingerprint changes, create a new collection, reembed,
verify record counts and representative searches, then switch only after user
approval. Keep the old collection/cache for rollback. Never overwrite a user's
existing Collection or mutate native Codex storage.
