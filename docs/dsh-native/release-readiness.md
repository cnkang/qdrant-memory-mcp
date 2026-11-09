# Unified DSH bundle release acceptance

## Baseline and gaps (2026-11-09)

Live baseline: PR #81 `f2e6133ae5168c3b53e3587f872c73929e256eff`, Runtime main `6df73703419f061e77b9b640c15ddf6609d26e58`, official DSH `0.2.2-rc.1`, npm bundle `latest=0.1.6` (no `next`). PR #81 has 65 resolved review threads and no unresolved threads; successful fixture/CLI checks do not establish AgentLoop acceptance.

| Area | Verified gap | Required evidence |
| --- | --- | --- |
| Runtime | Source 0.6.1 is unpublished; existing integration pins 0.6.0 | Clean wheel/sdist install, HTTPS event lifecycle, exact-main required checks |
| AgentLoop | Native fixtures and CLI config composition only | Official AgentLoop, Provider requests, durable Session replay and teardown |
| Docker | Local daemon unavailable at baseline | Linux isolated Qdrant/HTTPS Owner execution and receipts |
| Cloud | Existing protected Codex workflow is not DSH acceptance | Protected main-only DSH Provider execution; no skipped-model PASS |
| npm | Configuration-only four-file payload | Same-name Host module, tarball inspection, install/update/rollback |
| Storage | Legacy launcher and Native HTTPS Owner can diverge | Explicit modes and rejection of mixed storage targets |
| History | Recovery scans the last eight completed turns on activation | Persisted activation boundary; no implicit backfill |
| Identity | One Owner credential represents one principal | Single trusted identity per DSH profile; no model-derived grants |
| Desktop | No GUI evidence | Manual checklist, separate from CI |

No PyPI/npm publication, tags, releases, PR merges, production profiles or real memory data are authorized by this acceptance work. Source-snapshot tests must remain distinguishable from public-wheel acceptance.

## Release decisions

All decisions start at NOT VERIFIED and require executed evidence before promotion. A missing Runtime public wheel blocks final npm Native acceptance; it does not block source tests. Protected Cloud acceptance cannot execute unmerged PR code with secrets.

| Decision | Status |
| --- | --- |
| RUNTIME_0_6_1_RELEASE_READY | NOT VERIFIED |
| PR_81_MERGE_READY | NOT VERIFIED |
| DSH_NATIVE_E2E_VERIFIED | NOT VERIFIED |
| BUNDLE_IN_PLACE_UPGRADE_SAFE | NOT VERIFIED |
| OLLAMA_CLOUD_ACCEPTANCE_VERIFIED | NOT VERIFIED |
| DSH_BUNDLE_NEW_VERSION_RELEASE_READY | NO |

## Implemented candidate

The candidate remains `@cnkang/qdrant-memory-dsh-bundle@0.2.0-rc.1`; the
Native source package remains private. One official patch row loads the Host
module. Default `legacy` retains the prepared launcher and four MCP tools
without an Owner credential. `native-owner` opens no MCP connection;
`unified-owner` uses the identical HTTPS endpoint and token for MCP and Native.
Legacy rejects enabled automatic features before starting a transport.

Node >=24.9.0 is checked at module load; `engines.dsh` pins 0.2.2-rc.1.
Older environments should retain 0.1.6. No mode copies, migrates or removes
existing profiles or embedding data. Stop the old route before changing modes;
do not layer the private Native package or old overlay on this Bundle.

The activation watermark uses DSH's official ignorable `PluginRecord` API.
The Session package is an optional Host peer, avoiding duplicate Session
classes and their private-field rejection. New Agents await the durable
watermark before work; first enable excludes prior turns, disable/re-enable
starts a new boundary, and HMR/resume retain the enabled boundary. Recovery
reads a Session once and drains batches of eight into the bounded live queue.
Backfill is not implemented. A monotonic completion cursor and bounded-range
Session reads remain performance work; no unbounded in-memory queue was added.

## Executed evidence

| Layer | Result and scope |
| --- | --- |
| Native tests | 44 tests: 26 existing contract fixtures plus 18 real AgentLoop tests; Node 24.18.0, official locked 0.2.2-rc.1 packages |
| Actual loop | Provider request contains injected memory and IDs; system messages retain their content; JSONL replay retains injected user messages; tool continuation recalls once; completed turns capture; failed/cancelled turns do not; delegated Agents have no automatic memory authority |
| History | First-enable exclusion, disabled history, HMR, actual persisted resume and fork, full process restart with eight uncaptured turns, 8/16/32/100-turn sequential and Owner-outage recovery |
| Docker | Real Qdrant 1.20.0, Client 1.20.0, one WriterLease/ledger, verified self-signed TLS Owner, separate device tokens, exact Qdrant ID/content and Owner receipt assertions |
| Real clients | DSH -> independent MCP, MCP -> DSH model request, DSH -> real Pi Host twice in fresh processes |
| Authorization | Private/project separation, read-only delete rejection, forged identity/scope rejection, foreign-ID delete rejection; invalid tokens denied for search, submit, status and retry |
| Runtime | Clean built 0.6.1 wheel; 76 isolated Owner/retry/gateway tests; public 0.6.0 -> source-built 0.6.1 data-preserving upgrade; see Runtime PR #130 |
| Python/package gates | 81 focused tests after version/path rejection additions; Ruff and actionlint |
| Official DSH client | Five existing official CLI/client/CRUD tests pass with the upgraded 0.2.2-rc.1 test lock |
| npm tarball | Exact six-file whitelist, symlink/path rejection, manifest validation, canonical Native byte comparison, SHA256; two fresh npm packs produce identical bytes |
| Upgrade/rollback | Actual official Plugin Manager: published 0.1.6 tgz -> candidate tgz -> 0.1.6 tgz -> remove; one stable entry throughout; synthetic profile sentinel retained; Host module imported through official profile package resolution |

The reviewed candidate archive SHA256 is
`5f682747835b7cd133002eacacdaaef06afb627bd93f7ee8e0e50f1837d3abc5`.
Files are `package.json`, `index.js`, `native/index.js`, `cordis.patch.yml`,
`README.md`, and `LICENSE`. Repository locks pin the source dependencies.
The release script accepts an rc version, requires the exact current main SHA,
and the draft-asset workflow now checks exact-SHA blocking CI before packing.
No npm or PyPI upload, tag, Release or merge has been performed.

## Runtime readiness

Runtime [PR #130](https://github.com/cnkang/hermes-plugin-qdrant-memory/pull/130)
fixes the real Client 1.20.0 / Server 1.15.5 mismatch by aligning test lanes on
1.20.0 with an immutable server digest. No compatibility warning is suppressed.
Its review follow-up validates each lane independently and rejects ten
single-lane drift mutations. The local corrected steady Soak passed over
68.621 seconds: 262 requests, zero unexplained failures, losses or duplicates.

The original failed-job rerun lacked aggregate artifacts. Corrected branch
Soak execution was refused by the `soak-local` main-only environment policy.
Keep that policy. After approved merge, rerun the corrected matrix and the
five required main-push workflows on the exact final SHA. The source-built
wheel is evidence for development, not public-wheel Native acceptance.

## Cloud acceptance

`dsh-native-cloud.yml` accepts only canonical-repository main `workflow_dispatch`
and checks out its exact reviewed SHA before entering `soak-cloud`. It installs
the public Runtime 0.6.1 wheel, not a Git fallback. The DSH official pi-ai
Provider uses `openai-completions` at the exact `https://ollama.com/v1` endpoint,
with an environment credential reference, zero Provider retries, at most eight
model calls, 1200 output tokens per call and a short job timeout. Credentials
are not written to profiles, container images or evidence.

No protected Cloud execution was possible from this unmerged branch, and the
required Runtime wheel is still unpublished. Cloud API compatibility, model
availability and real extraction remain NOT VERIFIED. The prepared smoke
path covers capture and fresh-Session recall, independent MCP/Pi context and
turns after disabling automation. It is not the full Cloud UPDATE/CONFLICT
and Hermes/Codex matrix; those scenarios remain NOT RUN and are release
blockers. Deterministic model tests and real Qdrant do not substitute for Cloud.

## Principal and storage review

One DSH profile represents one trusted identity. A Host token is not a grant to
every person using the Host. Each client uses its own device credential, and
the Owner policy supplies owner, logical agent, device, project/private scope
and write permission. No authorization identity is extracted from model text.
The Bundle never opens Qdrant or takes a writer lease; the one Owner does.
No migration is automatic. If an operator elects to move Legacy data, first
preview and back up through the Runtime's migration tools, verify destination
embedding dimensions/fingerprint, verify exact IDs/counts/scope, and retain the
old profile for rollback. This candidate provides no migration command.

## Measurements and limits

One local Node 24.18.0 Docker/TLS run measured a 389 ms recall request including
Python child startup and HTTPS negotiation, 111 ms status, 118 ms submit,
265 injected characters and 0.932 seconds for the DSH process. Recall n=1;
p50/p95 are therefore the same single observation, not a capacity estimate.
Deterministic Provider latencies were 0-8 ms; no token usage was returned, so
none is invented. Multi-Session throughput, separate child startup cost,
Cloud extraction/Owner relation latency and memory/RSS remain NOT MEASURED.
No performance optimization is justified by these samples.

## Remaining acceptance and Desktop checklist

- Run final-head Linux, macOS ARM64 and Windows CI, including Node 24.9.0.
- Verify the combined tarball's Native operation under the complete Host
  Loader, beyond module resolution/configuration and canonical source tests.
- Exercise in-flight takeover under the real Host. Existing narrow fixtures
  cover executing-capture ownership transfer, but are not real-Host evidence.
- Run Hermes -> DSH, DSH -> Hermes, and Codex -> DSH using actual Host paths;
  these directions remain NOT RUN, not Owner-API substitutes.
- Complete real Cloud UPDATE/CONFLICT, model-output and shared-context checks
  after the public Runtime wheel and reviewed main are available.
- Desktop manual: install 0.1.6, upgrade to candidate, inspect all default-off
  settings, use ordinary Legacy tools with no Owner token, explicitly select
  Unified Owner, enable capture/recall, open a fresh Session, verify exact IDs,
  disable automation, check GUI/CLI writer ownership for one profile, simulate
  Owner failure, rollback to 0.1.6 and remove; verify data remains throughout.

## Current GO/NO-GO

| Required decision | Status | Reason |
| --- | --- | --- |
| RUNTIME_0_6_1_RELEASE_READY | NO | Corrected exact-main gates and accepted main Soak remain outstanding |
| PR_81_MERGE_READY | NO | Final-head blocking CI and remaining real packaged Host coverage need review |
| DSH_NATIVE_E2E_VERIFIED | NOT VERIFIED | Core actual-loop/Docker evidence passed; full Host matrix above is incomplete |
| BUNDLE_IN_PLACE_UPGRADE_SAFE | NOT VERIFIED | Actual local install/upgrade/rollback passed; full platform and Desktop acceptance outstanding |
| OLLAMA_CLOUD_ACCEPTANCE_VERIFIED | NOT VERIFIED | Protected main/public-wheel dependency; full real-model matrix not executed |
| DSH_BUNDLE_NEW_VERSION_RELEASE_READY | NO | Runtime public wheel, complete Cloud, platform and Desktop gates outstanding |
