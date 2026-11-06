# Version compatibility and maintainer upgrade checklist

Inventory refreshed 2026-11-06 after Skills PRs #56 and #57 and MCP PR #79 were rebase-merged.
No host adapter release is synchronized by this task.

## Current version map

| Component | Current candidate pin | Evidence / compatibility boundary |
|---|---|---|
| Plugin | 0.1.3 candidate | Independent plugin version, bumped for the bundled Skill 0.4.1 update. Current GitHub Marketplace package is a lightweight source install. |
| MCP distribution | 0.3.1, tag commit `e106f7de29da1a4ef889ccd589bdc76bb5092d6a` | Metadata/stdio adapter; delegates all memory operations to the Runtime. |
| Runtime | 0.6.0, release commit `dee6777432f17523db75f6be32cf3ef15e48235c` | Authoritative Qdrant, embedding, scope, SQLite ledger, recovery and WriterLease implementation. |
| Skill | 0.4.1 candidate, merged Skills commit `fc8dea078f04d4ec2c90064676875f556ae6457e` | Guided operator workflows from PR #54, clarifications from PR #56, and the handoff export path fix from PR #57; the plugin snapshot matches all 21 source files. |
| Launcher | Plugin 0.1.3 source | Dependency-free Node ESM host adapter. The Desktop-only ZIP still requires a bundled or confirmed host Node runtime. |
| Python test matrix | 3.11 / 3.14 | Runtime PR #127 merged at `b05143da0311d956d8479024d2aeff8253dfb907`; exact-SHA run [42159067998](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/42159067998) passed Python 3.11/3.14 behavior and host-compatibility jobs, MCP protocol coverage, SonarCloud and the required security gate. Issue #118 remains open in GitHub as a tracking record. |
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

## Forward migration and rollback

Before capturing an embedding-migration snapshot, pause and drain every writer
targeting the source collection on every host. Runtime's `WriterLease` is a
local OS file lock and does not coordinate writers on other hosts. Keep all
writers paused through snapshot capture, re-embedding, record-count and
representative-search verification, and the user-approved switch to the new
collection. Resume writers only after cutover completes, targeting the selected
collection.

Keep the old plugin version and Runtime environment available. Before any
Runtime or embedding-pipeline upgrade, make and verify coordinated backups of
the user Profile and its Qdrant collection using their supported backup
procedures. The JSON/Markdown handoff export is not a backup of either and
cannot restore the Profile or collection. If an embedding fingerprint changes,
create a new collection, reembed, verify record counts and representative
searches, then switch only after user approval. Keep the old collection/cache
for rollback. Before recording the post-switch change list for a rollback, pause
every writer against both collections. Keep writers paused through
reconciliation and until the switch back is complete.
Warn the user that every memory change made after the switch — additions,
updates and deletions against the new collection — would be lost or reverted
by reactivating the old collection. Record and review those post-switch
changes while writers are paused, present a verified reconciliation plan that
reapplies every addition,
update and deletion to the rolled-back collection, and switch back only after
the user approves that plan. An equivalent atomic cutover may replace the
pause only if it prevents writes from being omitted from the approved
reconciliation plan or hidden by rollback. Never overwrite a user's
existing Collection or mutate native Codex storage.
