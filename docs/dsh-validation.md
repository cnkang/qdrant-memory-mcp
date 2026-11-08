# Cross-harness validation

Validation is separated into protocol tests, real dependency/model preparation,
and actual desktop conversations. No synthetic model fixture is described as a
real model/GUI acceptance result.

Earlier baseline checks: 94 Python distribution tests, 22 Node tests and two explicit
official DSH integration tests passed. WorkBuddy's deterministic connector build,
wheel/sdist build, metadata checks, Ruff and workflow lint also passed.

## DSH dependency update (2026-10-17)

The official `next` release [0.2.1-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.2)
passed all three real local acceptance tests: MCP Client lifecycle/CRUD/restart,
CLI overlay preservation, and packed Bundle installation/composition/removal.
The CLI, MCP Client and filesystem Skill provider are pinned together at that
version. The original validation used the OAuth advisory fix `2.2.0`.
The Bundle peer range retains the old RC line and explicitly admits the new RC line.
The old range does not include the new npm prerelease line.

The Desktop GUI evidence below remains for 0.2.0-rc.2. This update does not claim
new GUI acceptance. The independent floating `next` CI probe complements the
committed exact-version release gate. See [dependency maintenance](ci.md).

The updated distribution suite passed 141 tests. Ruff, actionlint, clean npm
installation, wheel/sdist builds and strict metadata checks also passed locally.

## Native lifecycle adapter preview (2026-11-08)

The current public DSH release is [`0.2.2-rc.1`](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2-rc.1),
published from tag commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db`. The
source checkout used for API verification is at merge commit
`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`. The npm `latest` and `next` tags
for `@deepseek-ai/dsh` both resolve to `0.2.2-rc.1`; its declared Node minimum
is `24.9.0`. The native adapter pins `@deepseek-ai/dsh-llm@0.2.2-rc.1`,
`@deepseek-ai/cordis@4.1.0`, and `@deepseek-ai/schemastery@3.19.0` exactly.

| Path | DSH line | Runtime requirement | Status |
| --- | --- | --- | --- |
| Published MCP Bundle and Python overlay | Existing exact tests remain on `0.2.1-rc.2` | Published MCP/Runtime interfaces | Supported path; unchanged |
| Native lifecycle adapter source | `0.2.2-rc.1`, Node `>=24.9.0` | Versioned `qdrant-memory/extraction-v1` Owner candidate events | Source merged; npm private; Runtime 0.6.1 merged but not yet on PyPI |
| DSH Core | Upstream release commit above | No changes | Not modified |

`integrations/dsh/package.json` and `cross-harness.yml` retain the legacy RC
lane. `integrations/dsh/native/package.json` and
[`dsh-native.yml`](../.github/workflows/dsh-native.yml) pin the current RC lane
and exercise Linux x64, macOS 15 arm64, and Windows x64. The native package's
unit fixtures validate event filtering, candidate bounds, default-off config,
fork and subagent exclusion, and untrusted-memory formatting. Those tests do
not use a live model, Owner, or GUI. Published Runtime support and
real-model/desktop acceptance remain unverified; the native package has not
been published.

As of 2026-11-08, local evidence is 25/25 native unit fixtures on Node
24.22.1, 22/22 Runtime Owner lifecycle tests, and 5/5 MCP cross-harness contract
tests. The exact Node 24.9.0/pnpm 11.28.5 profile install/config/remove result is
Linux x64 only; macOS 15 arm64 and Windows x64 ran Node 24 (latest 24.x), not
the exact patch floor. See
[run 42472714839](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42472714839).
The floating `next` probe and legacy cross-harness lane also passed. See the
bilingual [native validation report](dsh-native/validation.md) and
[中文验证报告](dsh-native/validation.zh-CN.md) for coverage limits and release
blockers. The native source is merged, but the npm package and Runtime 0.6.1
remain unpublished; the native preview is not release-ready.

## Local automated coverage

The current test lock uses a temporary MCP Client `2.3.0` override for the cross-origin redirect fix.
Core also resolves to `2.3.0`. The three official DSH packages remain at `0.2.1-rc.2`.
The override affects development tests. It does not add dependencies to the configuration-only Bundle.

A separate Office dependency override selects `fflate 0.8.3` for `@deepseek-ai/libreoffice-kit`.
Clean installation and `npm audit` reported zero vulnerabilities on 2026-10-20 (UTC).
The Office parser passed a ZIP roundtrip with Unicode text and binary data.
It also rejected a malformed ZIP64 archive within the test timeout.
See [dependency maintenance](ci.md) for the advisory and removal condition.

| Layer | Verified behavior |
| --- | --- |
| Existing Python MCP | Four schemas, CRUD, fixed scope, WriterLease, redaction, restart/recovery and protocol-only stdout |
| Node bridge | Exact Runtime schema parity. Cold handshake while preparation is pending. No queued writes. Installed-Python CRUD/restart and writer exclusion |
| Provisioning | Verified bootstrap/archive, hash-locked Python dependencies/build tools, private paths, credential isolation and independent host profiles |
| Real CPU preparation | Fresh private Python and Runtime installation, verified CPU model, both host profiles, real inference, fresh-process save/search/update/delete |
| Public npm launcher | The exact connector command and the exact DSH command run through `npx` against the published `0.1.0-rc.1` package: cold handshake within the connector timeout, a clean unprepared probe (no downloads, no lock, no fake success), background preparation, refused-but-not-replayed writes, CRUD and fresh-process persistence on Linux, macOS and Windows. The pinned `0.1.0-rc.2` re-ran the same acceptance after its publication and passed on all three platforms (2026-10-16) |
| Launcher distribution | At the `0.1.0-rc.1` and `0.1.0-rc.2` releases, a clean `npm pack` of `integrations/managed/` reproduced the published tarball integrity, and the release workflow refuses unpublished pins |
| DSH 0.2.1-rc.2 official client | Real Cordis plugin activation/disposal, temporary probe, four tool registration/schema/rendering, error propagation, pre-cancelled request, child crash/reconnect and fresh-process persistence |
| DSH official CLI | Overlay composition preserves the selected user's patch and unrelated profile patch |
| DSH Bundle install | Real `dsh plugin` install of the packed Bundle tarball into a disposable profile. The layer composes and removes cleanly |
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

The earlier extension-contract inspection checked official DSH master
`86a402200d95fecef4529d969836f1fe13c6cb0d` and the published `next` packages
0.2.0-rc.2. At that inspection, master declared the 0.2.1 alpha line and no
stable GitHub Release was available. That inspection is historical. The update
above records the current automated
package baseline. Tests pin exact npm versions rather than moving master or
the unsynchronized npm `latest` tags.

## Desktop acceptance

WorkBuddy 5.8.2 connected a custom managed-launcher source entry, discovered all
four tools and created an isolated WorkBuddy profile automatically. Its actual
model saved and searched Chinese/English synthetic facts. A fresh conversation,
without the earlier transcript, retrieved the facts and used them to answer the
requested weekdays. Full WorkBuddy quit released the launcher process.

After relaunch, preparation was explicitly repaired/reconnected during a dependency
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
full desktop exit, backend diagnostics could reopen storage successfully.

After relaunch, a new session loaded the canonical Skill through DSH's standard Skill
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

Launcher `0.1.0-rc.1` and the pinned `0.1.0-rc.2` (a Windows rename-retry
hardening for interrupted preparation) are public on npm. The release
workflow refuses unpublished pins. The Runtime wheel is public on PyPI. The
MCP distribution `v0.1.4` is published on PyPI and the MCP Registry, and its
GitHub Release carries the connector assets (2026-10-16). The DSH Bundle
0.1.1 is published on npm (2026-10-18), and its GitHub Release carries the
tagged tgz and checksum.

The remaining gates include marketplace review, import with managed Node in WorkBuddy, and a full restart on a clean machine.
They also include installer-crash recovery, dispatch-time cancellation, HMR/profile-switch cases, and production upgrade or rollback.
Cloud multi-writer sharing is not implemented. The published Runtime and
published DSH MCP paths do not automatically capture or prefetch conversation
turns. The separate native preview adds an opt-in source implementation, but it
is not usable with current published Runtime packages and is not release or
acceptance evidence.

Keep one active owner for embedded storage. Do not bypass locks or reuse Hermes
profiles implicitly. See [Hermes compatibility](hermes-compatibility.md),
[installation](dsh-integration.md) and [Python/Node decision](adr/0001-python-runtime-and-node-launcher.md).
