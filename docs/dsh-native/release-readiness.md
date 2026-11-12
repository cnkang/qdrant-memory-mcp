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

The statements in this 2026-11-09 baseline record what had not yet been done at that point. Runtime 0.6.1 has since been released independently; that release does not establish DSH Cloud, platform or Desktop acceptance. Source-snapshot tests must remain distinguishable from public-wheel acceptance.

## Release decisions

Runtime 0.6.2 is now published and verified from PyPI, and MCP PR #81 is merged. This supersedes the 0.6.1 prerequisite while clearing Runtime publication only; it does not establish final DSH Native acceptance. A protected main Cloud smoke now passes with the public Runtime 0.6.2 wheel, but the full Cloud and cross-client matrix remains outstanding.

| Decision | Status |
| --- | --- |
| RUNTIME_0_6_2_PUBLIC_WHEEL | YES |
| PR_81_MERGE_READY | MERGED |
| DSH_NATIVE_E2E_VERIFIED | NOT VERIFIED |
| BUNDLE_IN_PLACE_UPGRADE_SAFE | NOT VERIFIED |
| OLLAMA_CLOUD_ACCEPTANCE_VERIFIED | NOT VERIFIED |
| DSH_BUNDLE_NEW_VERSION_RELEASE_READY | NO |

Runtime 0.6.2 is tagged at source SHA
`913fa705922b5bfeb29d52f102cfc6385a4d0436`; its public PyPI wheel SHA256 is
`4606d1529092104d5594866032c61a02376c127f2ffc483c0442a7549b40c264`.
PR #95 updates the protected DSH Cloud workflow to install that public wheel
and checks out the same immutable Runtime SHA only for `tests/helpers.py`.
The DSH Owner implementation is imported from the installed wheel. The
post-merge protected main-only smoke passed; this is partial Cloud evidence,
not final DSH acceptance.

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
| Native tests | 45 tests: 26 existing contract fixtures plus 19 real AgentLoop tests; Node 24.18.0, official locked 0.2.2-rc.1 packages |
| Actual loop | Provider request contains injected memory and IDs; system messages retain their content; JSONL replay retains injected user messages; tool continuation recalls once; completed turns capture; failed/cancelled turns do not; delegated Agents have no automatic memory authority |
| History | First-enable exclusion, disabled history, HMR, actual persisted resume and fork, real Agent takeover during an executing capture, full process restart with eight uncaptured turns, 8/16/32/100-turn sequential and Owner-outage recovery |
| Docker | Real Qdrant 1.20.0, Client 1.20.0, one WriterLease/ledger, verified self-signed TLS Owner, separate device tokens, exact Qdrant ID/content and Owner receipt assertions |
| Real clients | DSH -> independent MCP, MCP -> DSH model request, DSH -> real Pi Host twice in fresh processes |
| Authorization | Private/project separation, read-only delete rejection, forged identity/scope rejection, foreign-ID delete rejection; invalid tokens denied for search, submit, status and retry |
| Runtime | 76 isolated Owner/retry/gateway tests; public 0.6.0 -> source-built 0.6.1 data-preserving upgrade; Runtime 0.6.1 wheel and sdist are now published and fresh-installed from PyPI; full six-lane Soak and exact-SHA release gates passed (details below) |
| Python/package gates | 81 focused tests after version/path rejection additions; Ruff and actionlint |
| Official DSH client | Five existing official CLI/client/CRUD tests pass with the upgraded 0.2.2-rc.1 test lock |
| npm tarball | Exact six-file whitelist, symlink/path rejection, manifest validation, canonical Native byte comparison, SHA256; two fresh npm packs produce identical bytes |
| Upgrade/rollback | Actual official Plugin Manager: published 0.1.6 tgz -> candidate tgz -> 0.1.6 tgz -> remove; one stable entry throughout; synthetic profile sentinel retained; Host module imported through official profile package resolution |
| Packed Unified Owner | Actual tarball installed by the official Plugin Manager, then imported with the official package resolver into the real AgentLoop: four real HTTPS MCP tools, automatic recall/capture against the same Owner, exact new Qdrant record, and clean tool removal/ordinary conversation on unload |

From exact MCP main SHA `84ba8cb8b32679265077c1af0ff0187f04dcb480`, two fresh
packer runs produced byte-identical candidate archives. The current archive
SHA256 is `d0d3ab7e58d95372930493030bdfa02410ca690ab0b9b3d00f50351d92beac2b`;
its SRI is `sha512-UXeN22ZNS0TeMXQ5PSEVs/C+rct44hXY+0K6vDZysaV9QViTY9TG5G/EwAYFaOag2Ik+/Pe9KKJLkd9T7PIAVQ==`.
Files are `package.json`, `index.js`, `native/index.js`, `cordis.patch.yml`,
`README.md`, and `LICENSE`. Repository locks pin the source dependencies.
The release script accepts an rc version, requires the exact current main SHA,
and the draft-asset workflow now checks exact-SHA blocking CI before packing.
No DSH bundle npm candidate has been published; the public DSH bundle remains at 0.1.6. Runtime 0.6.1 was released separately as documented below.

Full ordinary Python source suite after rebuilding current distributions:
409 passed, one existing platform-specific skip. The external Docker acceptance
is explicitly invoked by its dedicated blocking workflow, not collected by
the ordinary Python distribution suite. Fresh sdist inspection confirms that
neither its external harness nor npm lockfiles ship to PyPI.

## Runtime readiness

Runtime [PR #130](https://github.com/cnkang/hermes-plugin-qdrant-memory/pull/130)
fixes the real Client 1.20.0 / Server 1.15.5 mismatch by aligning test lanes on
1.20.0 with an immutable server digest. No compatibility warning is suppressed.
Its review follow-up validates each lane independently and rejects ten
single-lane drift mutations. The local corrected steady Soak passed over
68.621 seconds: 262 requests, zero unexplained failures, losses or duplicates.

The corrected release was validated on exact Runtime main SHA
`2696122405e3324a1e227c131e0f9b2a320dd23c`. The short Soak was inspected
before the full run. Full Soak [run 42989965437](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/42989965437)
passed all six 18,000-second lanes and the final report; all six smoke lanes
also passed. The five required exact-SHA main-push workflows passed. The
intentional network-fault lane logged its injected client disconnect; its
invariants showed no loss, duplicate, cross-scope leak or unexplained failure.

The protected release workflow
[run 43038295736](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/43038295736)
used the existing PyPI environment approval and Trusted Publishing. Tag
[`v0.6.1`](https://github.com/cnkang/hermes-plugin-qdrant-memory/releases/tag/v0.6.1)
and the GitHub Release point to that validated source SHA. PyPI now serves
[`hermes-plugin-qdrant-memory 0.6.1`](https://pypi.org/project/hermes-plugin-qdrant-memory/0.6.1/):
wheel SHA256 `5ad7835f454789c1bcb48d877a303ebb6f95e6084ab62d0ecaf50e4f44d26cc9`,
sdist SHA256 `4025497177f294dfe586f36756d29af2397844027a0f18def05eb6befd16fc1a`.
A clean public-PyPI installation, `pip check`, CLI help, and isolated status
command passed. Runtime main later advanced to
`5f72ee962b06f2acb7986556bbb54b6da02d1a0e` for a release-evidence documentation
change; the release tag remains pinned to the Soak-validated SHA above.

MCP PR [#81](https://github.com/cnkang/qdrant-memory-mcp/pull/81) was merged
at `6f8e57383b760668abe7aa52f4d3c865f8d762e5`. The current DSH Native CI
[run 42985549290](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42985549290)
passed on MCP main `28f14f727eb224b8777b1c90cffb4be5ee0156b9`.

## Cloud acceptance

`dsh-native-cloud.yml` accepts only canonical-repository main `workflow_dispatch`
and checks out its exact reviewed SHA before entering `soak-cloud`. The candidate
workflow installs the public Runtime 0.6.2 wheel, not a Git fallback; the exact
0.6.2 source checkout is used only to load `tests/helpers.py`. The DSH official
pi-ai Provider uses `openai-completions` at the exact `https://ollama.com/v1` endpoint,
with an environment credential reference, zero Provider retries, at most eight
model calls, 1200 output tokens per call and a short job timeout. Credentials
are not written to profiles, container images or evidence.

Protected DSH Cloud run
[43303663019](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43303663019)
reached Ollama Cloud but failed because the extractor omitted the fixture-only
leading `Synthetic ` label while preserving the fact. Separately, the packed-
bundle E2E test exposed that a process-local receipt list cannot observe a
separate Owner process; PR #95 changes that assertion to query the real Owner.
Both are test-observation defects, not evidence of data loss or an access
control failure. Those failed runs are not passes and do not establish the full
Cloud matrix. PR #95 also pins the post-merge workflow to the public Runtime 0.6.2
wheel.

Protected main-only Cloud run
[43326521742](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43326521742)
passed at exact MCP SHA `84ba8cb8b32679265077c1af0ff0187f04dcb480` after the
`soak-cloud` environment approval. It installed the public Runtime 0.6.2 wheel
and official DSH `0.2.2-rc.1`, used the configured Ollama Cloud
`deepseek-v4.1-flash` model, and passed one pytest case with zero failures or
skips. The real DSH AgentLoop extracted a synthetic fact into the HTTPS Owner;
a fresh MCP process recalled the exact persisted Qdrant ID. The run also
verified the separate Pi process path twice, scope isolation, Owner event
receipts and retry idempotency, permission rejection, and capture through the
packed Unified Bundle. The report records eight model calls across the DSH and
packed-bundle loops. Artifact `dsh-cloud-synthetic` has SHA256
`8f09dd5d9030cedf0e319c77890168abdd7a7a829c4ea36290405af47b9f34eb`.

This is a successful configured-model smoke, not the full Cloud matrix. Its
directions report DSH->MCP, MCP->DSH and DSH->Pi as PASS, while Hermes->DSH and
Codex->DSH remain NOT RUN. Cloud UPDATE/CONFLICT and complete cross-client
acceptance also remain outstanding. Deterministic model tests and real Qdrant
do not substitute for those paths.

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
- Run Hermes -> DSH, DSH -> Hermes, and Codex -> DSH using actual Host paths;
  these directions remain NOT RUN, not Owner-API substitutes.
- Complete real Cloud UPDATE/CONFLICT, model-output and shared-context checks
  on reviewed MCP main with the public Runtime 0.6.2 wheel.
- Desktop manual: install 0.1.6, upgrade to candidate, inspect all default-off
  settings, use ordinary Legacy tools with no Owner token, explicitly select
  Unified Owner, enable capture/recall, open a fresh Session, verify exact IDs,
  disable automation, check GUI/CLI writer ownership for one profile, simulate
  Owner failure, rollback to 0.1.6 and remove; verify data remains throughout.

## Current GO/NO-GO

| Required decision | Status | Reason |
| --- | --- | --- |
| RUNTIME_0_6_2_PUBLIC_WHEEL | YES | Published from exact source SHA `913fa705922b5bfeb29d52f102cfc6385a4d0436`; clean public wheel SHA256 `4606d1529092104d5594866032c61a02376c127f2ffc483c0442a7549b40c264` |
| PR_81_MERGE_READY | MERGED | MCP PR #81 merged at `6f8e57383b760668abe7aa52f4d3c865f8d762e5` |
| DSH_NATIVE_E2E_VERIFIED | NOT VERIFIED | Core actual-loop/Docker evidence passed; full Host matrix above is incomplete |
| BUNDLE_IN_PLACE_UPGRADE_SAFE | NOT VERIFIED | Actual local install/upgrade/rollback passed; full platform and Desktop acceptance outstanding |
| OLLAMA_CLOUD_ACCEPTANCE_VERIFIED | NOT VERIFIED | Protected run 43326521742 passed one configured-model synthetic smoke at exact main SHA `84ba8cb8b32679265077c1af0ff0187f04dcb480`; full UPDATE/CONFLICT and Hermes/Codex paths remain incomplete |
| DSH_BUNDLE_NEW_VERSION_RELEASE_READY | NO | Full Cloud, platform, cross-client and Desktop gates remain outstanding; public npm bundle stays at 0.1.6 |
