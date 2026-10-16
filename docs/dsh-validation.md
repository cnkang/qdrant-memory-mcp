# Cross-harness validation

Validation is separated into protocol tests, real dependency/model preparation,
and actual desktop conversations. No synthetic model fixture is described as a
real model/GUI acceptance result.

Local final checks: 94 Python distribution tests, 22 Node tests and two explicit
official DSH integration tests passed. WorkBuddy's deterministic connector build,
wheel/sdist build, metadata checks, Ruff and workflow lint also passed.

## Local automated coverage

| Layer | Verified behavior |
| --- | --- |
| Existing Python MCP | Four schemas, CRUD, fixed scope, WriterLease, redaction, restart/recovery and protocol-only stdout |
| Node bridge | Exact Runtime schema parity. Cold handshake while preparation is pending. No queued writes. Installed-Python CRUD/restart and writer exclusion |
| Provisioning | Verified bootstrap/archive, hash-locked Python dependencies/build tools, private paths, credential isolation and independent host profiles |
| Real CPU preparation | Fresh private Python and Runtime installation, verified CPU model, both host profiles, real inference, fresh-process save/search/update/delete |
| Public npm launcher | The exact connector command and the exact DSH command run through `npx` against the published `0.1.0-rc.1` package: cold handshake within the connector timeout, a clean unprepared probe (no downloads, no lock, no fake success), background preparation, refused-but-not-replayed writes, CRUD and fresh-process persistence on Linux, macOS and Windows. The pinned `0.1.0-rc.2` re-runs the same acceptance after its publication |
| Launcher distribution | At the `0.1.0-rc.1` release, a clean `npm pack` of `integrations/managed/` reproduced the published tarball integrity; the same check re-runs for the pinned `0.1.0-rc.2` after its publication, and the release workflow refuses unpublished pins |
| DSH 0.2.0-rc.2 official client | Real Cordis plugin activation/disposal, temporary probe, four tool registration/schema/rendering, error propagation, pre-cancelled request, child crash/reconnect and fresh-process persistence |
| DSH official CLI | Overlay composition preserves the selected user's patch and unrelated profile patch |
| DSH Bundle install | Real `dsh plugin` install of the packed Bundle tarball into a disposable profile; the layer composes and removes cleanly |
| DSH Skill provider | Canonical Skill discovery/loading by the actual filesystem provider |
| WorkBuddy packaging | Canonical Skill 0.2.6 at exact commit, deterministic ZIP/checksum and existing publication guards |
| Hermes native source | 431 passed, 6 skipped: native lifecycle/defaults/models, scope, ownership, ledger/recovery and standalone MCP. External-service/real-model skips remain separate gates |
| OpenCode 2.0.24 | Real isolated CLI registration, API connection and connected status |
| Pi 1.1.0 | Real isolated CLI four-tool discovery. 14 SDK Skill discovery/reference/read-loop tests use a scripted local model transport |

The first managed CPU run completed both-host acceptance in 276 seconds. The
hash-locked rerun, using a fresh program environment and retained verified model
cache, completed in 219 seconds. These macOS Apple Silicon measurements are
examples, not a startup-time promise for other networks/platforms.
The subsequent fresh-root run that interrupted/resumed installation completed in
268 seconds and passed both-host persistence.

DSH client tests use the official package and real stdio processes. A fixture
tool registry provides an observation seam. Those tests do not exercise the
whole AgentLoop or every permission policy. Pre-cancellation is tested.
Cancellation of a dispatched durable write can have an uncertain outcome. The
caller must check the exact operation and its ID before any repeat. Do not
repeat an uncertain write unless a repeat is safe for that operation. No write replay is added by the adapter.

The real cold-install CI also aborts preparation immediately before Runtime
installation, then resumes the same partial environment. A completion marker is
required before any MCP backend can execute. Interrupted preparation cannot be
mistaken for an installed Runtime.
The same CI test leaves truncated legacy installation metadata and stale temporary
files. It then verifies that preparation restores the exact dependency snapshot
and completes installation before backend startup. Unit tests also inject a partial
write followed by a disk-full error and verify that a later retry succeeds.

The extension contracts were checked against official DSH master
`86a402200d95fecef4529d969836f1fe13c6cb0d` and the published `next` packages
0.2.0-rc.2. Master declares the 0.2.1 alpha line. No stable GitHub Release was
available at inspection. Tests pin the actual desktop-compatible npm version,
not the moving master branch or a misleading npm `latest` tag.

## Desktop acceptance

WorkBuddy 5.8.2 connected a custom managed-launcher source entry, discovered all
four tools and created an isolated WorkBuddy profile automatically. Its actual
model saved and searched Chinese/English synthetic facts. A fresh conversation,
without the earlier transcript, retrieved the facts and used them to answer the
requested weekdays. Full WorkBuddy quit released the launcher process. After
relaunch, preparation was explicitly repaired/reconnected during a dependency
environment change. Actual GUI searches confirmed the same records and IDs.
Exact-ID update/delete and subsequent searches then passed. This is a
restart/recovery result, not an uninterrupted cold-install UX certification.
The GUI used an explicitly selected existing Node executable
and shared pre-provisioned program/model files. This is not marketplace ZIP
import, managed-Node provisioning or a clean-machine one-click certification.

DeepSeek Harness Desktop 0.2.0-rc.2 installed a local configuration-only Bundle
through its Plugin Manager and activated the official MCP client. The actual
model saved/searched two synthetic facts. A fresh session retrieved and used
them without the previous transcript. Exact-ID update preserved the first ID,
and exact-ID deletion removed the second from subsequent search. After a verified
full desktop exit, backend diagnostics could reopen storage successfully. After
relaunch, a new session loaded the canonical Skill through DSH's standard Skill
tool, recalled the updated record and continued to exclude the deleted ID.
The test used
the prepared CPU Runtime and a dedicated DSH profile. No DSH core changes were
needed. Remaining desktop lifecycle and platform cases are separate release gates.

Both temporary desktop connections were disabled after acceptance. Independent
CLI diagnostics and searches then reopened each profile and confirmed one
remaining synthetic record with the expected original ID and updated text. They
also confirmed normal ownership release. Private configuration, raw transcripts and test data
are excluded from Git and distribution archives.

## Continuous integration

[`cross-harness.yml`](../.github/workflows/cross-harness.yml) runs:

- Linux x64, Windows x64 and macOS Apple Silicon shared/WorkBuddy/DSH protocol tests.
- Exact npm DSH client/CLI/filesystem-provider packages from a lockfile.
- Real CPU preparation and both-host persistence on each native platform.
- Linux OpenCode/Pi CLI compatibility, shared/private scope and canonical Pi SDK Skill tests.

The integration jobs reject skipped or empty acceptance reports. Native cold
setup runs on push/PR. Manual dispatch can opt into it with `cold_setup`.
CI is reproducible evidence only after the exact commit's jobs finish. A queued
or pending workflow is not a passing result. Ordinary protocol tests use a
synthetic embedding HTTP fixture, with no cloud keys or user profiles.

## Remaining release gates

Launcher `0.1.0-rc.1` is public on npm. Launcher `0.1.0-rc.2` — a Windows
rename-retry hardening for interrupted preparation — is pinned by the
connector and the Bundle and must be published before release assets are
prepared. The release workflow refuses unpublished pins. The Runtime wheel is
public on PyPI. The MCP distribution 0.1.4 and the DSH Bundle 0.1.0 are
prepared for publication with this round. The published Python MCP remains
0.1.3 until its tag exists. Marketplace listing review, managed Node GUI
import in WorkBuddy, full application restart on a clean machine, forced
installer-crash recovery, dispatch-time cancellation, every HMR/profile-switch
case, and production upgrade/rollback remain separate release gates. Cloud
multi-writer sharing and automatic DSH extraction/prefetch are not implemented.

Keep one active owner for embedded storage. Do not bypass locks or reuse Hermes
profiles implicitly. See [Hermes compatibility](hermes-compatibility.md),
[installation](dsh-integration.md) and [Python/Node decision](adr/0001-python-runtime-and-node-launcher.md).
