# Qdrant Memory for Codex: engineering and acceptance record

Date: 2026-11-04 (Asia/Singapore). Candidate: plugin 0.1.1. This is an engineering
candidate, not an approved OpenAI public-directory release. Runtime, MCP and
adapter publications follow their separate versioned release gates; they do not
constitute Codex Marketplace submission. Earlier dated entries retain their
original source versions and evidence.

**One Memory. Multiple Agents. No Lock-in.** Standard readable exports and
harness adapters belong to the product contract. Supported native APIs should
be used where they exist; unavailable APIs must never be simulated. Users keep
their sources, Qdrant data and exports after uninstalling. Current adapters are
Runtime/Mem0 JSON and Codex semantic artifacts, not a claim of universal native
write support for every harness.

## Protected cloud acceptance

The MCP repository's `codex-plugin-cloud.yml` workflow validates its own reviewed
`main` with the Runtime revision declared in the plugin's fixed requirements.
It is manual-only, checks the exact event/repository/ref before checkout, and
uses the protected `soak-cloud` environment. The Runtime repository's separate
lane validates its own exact `main` implementation against a pinned client.

Configure the MCP repository environment with these values:

| Type | Name | Value |
|---|---|---|
| Variable | `SOAK_LLM_BASE_URL` | `https://ollama.com/v1` |
| Variable | `SOAK_LLM_MODEL` | A non-GPT cloud model ID, for example `deepseek-v4.1-flash` |
| Secret | `SOAK_LLM_API_KEY` | Ollama Cloud API key |

Restrict deployment branches to `main` and retain required reviewers. Qdrant and
embedding fixtures are local and synthetic; no Qdrant Cloud or OpenAI credentials
are needed. A normal credential-free PR check does not establish a cloud pass:
the manual workflow publishes its explicit outcome as a result artifact.

The first Runtime-hosted cloud run, `41744250983`, failed before model calls
because the isolated `CODEX_HOME` did not exist. The harness now creates that
private directory before invoking Codex. This failure does not establish an
Ollama/model compatibility result.

The MCP-hosted [run 41768867472](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/41768867472)
passed at source `2da4ec66255467e28867b589e2b61895d0debe16`, using Codex CLI
0.165.0 and Ollama Cloud `deepseek-v4.1-flash`. It installed the declared
Runtime adapter source `e8d3b15ea2ce6be0a9e59563cf031b1987991a6d` with metadata
0.5.5; this does not establish native support in the older public 0.5.5 wheel.
The result verified one actual call for each add/search/update/delete, target
identity and final stored state, distinct v1/v2 fixtures, three-record handoff
fidelity and data preservation after uninstall. Handoff remained HANDOFF_PENDING
with native_verified=false. This is cloud CLI acceptance, not Desktop UI or
native adoption evidence. Repeat acceptance after final release pins change.

The synthetic MCP call-count lane disables the automatic skills instruction
block (`skills.include_instructions=false`) so the model is evaluated only on
the explicitly requested operation. Plugin skills remain shipped and are
covered by their own build checks; this lane does not claim skill-following
behavior. The lane also disables the one-second optional-MCP startup grace
(`mcp_optional_startup_grace_ms=0`) so a cold Runtime launch is not silently
omitted from the tool catalog.

## Inventory and architecture

The source pins below now identify merged upstream main commits. Earlier
acceptance entries retain their original revisions; they are historical evidence
rather than claims that every model run used the refreshed pins.

| Component | Verified baseline / decision |
|---|---|
| Runtime | Public release 0.5.5; merged adapter pin `e8d3b15ea2ce6be0a9e59563cf031b1987991a6d` |
| MCP distribution | Public release 0.2.9; remains metadata-only on PyPI |
| General skill | Merged source snapshot `c9f95154f217b8110c4081981d8be6f6083b3c91`, metadata 0.3.8 |
| Official Codex source inspected | `616cab3a3529f572c3385098c12698278770ea98` |
| Local client/runtime | Codex CLI 0.165.0; Node 22.23.2; fresh private Python 3.11.15 environment |
| Native layouts | v1 MEMORY.md with summary fallback; v2 consolidated memory_summary.md; evidence/raw chats excluded |
| Plugin format | Portable Agent Plugins 1.0 plus synchronized Codex env_vars overlay; one stdio backend |
| Implementation | Dependency-free Node host boundary; existing Python Runtime owns embedding, scope, schema, ledger, lease and recovery |

## Merge-gate follow-up (2026-11-04, UTC+8)

- Runtime PR #119 and skill PR #46 were rebase-merged after their hosted checks
  and SonarCloud gates passed. Runtime's final reviewed tree had zero open Sonar
  findings and a CodeRabbit approval; native Windows ran 41 checks without skips
  for Python 3.11/pywin32 312 and Python 3.14/pywin32 311/312.
- The MCP source reader now holds checked ancestors until descriptor reads end
  and compares opened-file identity with the preceding no-follow stat. The local
  source/acceptance follow-up passed CodeRabbit CLI review with zero findings.
- The final local MCP suite passed 245 tests with one environment-dependent skip.
  The follow-up CodeRabbit CLI review of the archive snapshot, workflow failure
  propagation, isolated preview and export-fidelity fixes completed with zero
  findings. Dry-run checks now assert unchanged records and zero embedding calls;
  handoffs must preserve every exported ID, text and scope before and after
  uninstall.
- Real Codex CLI 0.165.0 subscription acceptance against merged Runtime
  `e8d3b15ea2ce6be0a9e59563cf031b1987991a6d` passed all four scoped tools using
  synthetic local HTTP embeddings. v1 and v2 imported distinct green/amber facts;
  the three-record handoff verified before and after uninstall, and stored data
  was preserved. No subscription credentials entered GitHub CI.
- The refreshed MCP candidate's hosted gates remain pending. No registry,
  Marketplace or tagged release was published by this follow-up.

Node is a project choice for the host boundary. Official plugin/MCP packaging is
language-neutral; no requirement to rewrite the existing Python Runtime was found.
The existing managed WorkBuddy/DSH launcher was inspected and remains unchanged.
Its old Runtime snapshot and auto-setup semantics were not silently reused.

Runtime Issue #115 and PRs #116/#117 remained OPEN when rechecked. The original
Runtime checkout's `codex/ci-infra-retry` branch and its unpushed commit were
preserved; this task's branch started from origin/main. No production memory or
collection was used for destructive tests.

## IMPLEMENTED

- Portable plugin manifest, MCP registration, GitHub/repository Marketplace,
  independent version, onboarding, migration and backup/exit skills, bilingual
  plugin README, ADR and public-directory checklist.
- Archive builder vendors the exact upstream skill snapshot and emits source
  commit, component checksums and an archive SHA-256. Host-normalized manifests
  are identified separately because Plugin Creator normalizes publisher and
  compatibility metadata. Actual source ZIP manifests are schema-validated.
- Read-only native artifact adapter in the sole Runtime, explicit CODEX_HOME,
  config-only version/enablement inspection, deterministic content-derived IDs,
  duplicate source mappings, file/content hashes and provenance.
- Existing SQLite migration manifests/operations, failure recovery, resume,
  retry-failed, verification, fixed profile scope and WriterLease. Source text
  is never written to native files. Sensitive patterns/code fences are skipped;
  manual privacy review remains required.
- Scoped JSON/Markdown exit bundle, per-record/file checksums, no-clobber output,
  verification and HANDOFF_PENDING status. Runtime's ordinary JSON remains
  usable for imports into this suite and other compatible harnesses.
- CPU-default onboarding and explicit Ollama/OpenAI-compatible alternatives,
  Runtime fingerprint validation and the new-collection/re-embedding rollback
  workflow. There is no credential inheritance or unverified native embedding
  option. Model downloads require approval and never fall back to cloud.
- Existing Shared Owner bridge selection in the launcher. It does not open a
  second independent writer when an authorized Owner URL is configured.
- Credential-free real CLI CI in the MCP repository. Separate manual cloud lane
  in Runtime reuses the existing protected `soak-cloud` environment and a pinned
  client commit. Only synthetic facts go to the Ollama model; Qdrant is isolated
  embedded storage and embeddings are a local HTTP fixture in that lane.

## TESTED

| Evidence | Executed outcome |
|---|---|
| Runtime migration/standalone, inventory and cloud-boundary suite | **410 passed** locally, real Qdrant/SQLite and Hermes import path |
| Cloud workflow boundary test (included above) | **1 passed**, main-only/manual/environment/immutable code constraints |
| MCP repository suite | **231 passed**, including coverage collection; native Pi handoff was explicitly outside this run |
| Package source boundary | Plugin skills allowed only in the four intended directories; wheel remains metadata-only; plugin excluded from sdist |
| Build checks | Rebuilt wheel/sdist; metadata verifier and strict Twine checks passed |
| Portable schemas | Root plugin.json and mcp.json validated against official Agent Plugins 1.0 JSON Schemas |
| Lint | Changed Python passed Ruff lint/format; both Codex workflows passed actionlint |
| Actual CLI install | Isolated CODEX_HOME; marketplace add, plugin add, setup file present and declared in manifest, persisted disable, uninstall passed; client skill discovery is not inferred |
| Actual subscription account | Existing local ChatGPT login; real Codex CLI model invoked add/search/update/delete on the plugin server; separate sessions retrieved persisted synthetic facts |
| Native round trip | Synthetic v1/v2 source deduplicated to one imported record; combined with a newly added fact; exported two records; handoff verified before and after uninstall; source/export files preserved |
| Source protection | Dry-run zero destination writes, symlink/corrupt/unknown input cases, code/credential exclusions, exact scope, interrupted migration retry, repeated resume and handoff checksum/no-clobber tests passed |
| Fresh CPU environments | Runtime commit above passed hosted macOS, Linux and Windows fresh dependency installation, pinned model download, real offline CPU and MCP acceptance with no skipped model tests |

CPU evidence: [three-platform real model run](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/41593674109).
The CPU run used `f501a6d2891c641d22a47856a3193761df7a4557`; the later adapter
pin adds topic filtering and the cloud workflow without changing CPU/embedding
implementation. This is Runtime CPU evidence. The local subscription-account plugin test used
the explicitly labeled synthetic embedding fixture, not CPU inference.

The account harness uses `--ignore-user-config`, an explicit test Marketplace,
no unrelated MCP servers/plugins, disabled native-memory use/generation and
ephemeral chats. Existing auth is used by Codex without being read or copied.
Only the four test-plugin tools receive an invocation-local approval policy for
the already authorized synthetic operations. No persistent broad approval or
production storage configuration is added. Initial failed probes are not counted
as passes; they found environment filtering, source registration and tool-approval
requirements that the final harness handles explicitly.

## Review follow-up validation

PR #67 review `5748890421` was checked against current source. All eleven inline
comments and four follow-ups were valid on the reviewed revision; none were
discarded based on their severity labels:

| Reviewed concern | Fix and evidence |
|---|---|
| sdist excludes precede includes | Reordered directives; rebuilt actual wheel/sdist and asserted absence of Codex development files |
| Chinese embedding-switch guidance | New collection/profile and preserved rollback collection now match English guidance |
| Verification path base | Both READMEs identify the plugin ZIP root |
| Bare migration commands | Skills and Chinese README use the full Runtime command and profile prefix |
| Optimized Python skips validation | Explicit exceptions; invalid manifest rejected under `python -O` |
| Evidence document missing from dirty check | Dirty check includes the document; test distinguishes clean build from evidence-only edit |
| Untracked private files packaged | Select git-indexed files; synthetic ignored/untracked private files excluded |
| Inherited Shared Owner route | Remove Owner URL/token from the test environment; regression asserts neither reaches commands |
| Subscription test removes an existing install | Fail before any mutation; regression verifies no install/remove or cleanup call |
| Install outside cleanup scope | Install after server/thread startup inside `try`; startup and setup failure regressions |
| Windows path assertion | Native Node paths and both executable layouts; no platform skip |
| Search accepts empty/wrong results | Parse MCP JSON and require actual stored ID, text and scope |
| Update/delete can be no-ops or target neighbors | Check exact arguments/result IDs and live full scoped inventory after each operation |
| Setup output overstates discovery | Report `setup_file_present`; workflow step and evidence use the same claim |
| Launcher checks tool count only | Assert all four exact tool names through the real Node MCP entrypoint |

The subsequent MCP review (5749701789) added eight inline findings and six
follow-ups. Verified fixes cover approved native-source arguments, symlinked
parent directories, a required pinned skill entrypoint, exact archive commit,
fixed ZIP timestamps/order/bytes, launcher search read-back, complete sdist
exclusion, mixed-scope search rejection, one requested operation per session,
native-import text fidelity, post-uninstall handoff count and optimized-Python
validation. Marketplace cleanup removes only a registration created by the test;
an existing registration is preserved, and a conflicting source fails before
installation. A local follow-up caught failed plugin removal; cleanup now checks
the exit result and preserves the registration while that plugin remains installed.

Runtime review 5749611122 added canonical profile reads in the export helper and
Markdown/JSON record-set consistency verification. The public CLI already expands
tilde paths; the direct helper now uses the same canonical path for configuration,
lease and recovery checks. Regressions cover reset and scope-delete intents, plus
missing/changed Markdown records with recomputed matching manifest hashes.

Local CodeRabbit review also identified the acceptance function-name shadow and
Unicode line-separator fence mismatch. Both were independently verified, fixed
and covered by regressions. Runtime reads now use one no-follow descriptor and
its metadata; handoff publication/verification share a separate 64 MiB per-file
bound checked before directory creation.

The hardened subscription acceptance passed again with Codex CLI 0.165.0 and the
publisher namespace `qdrant-memory@cnkang` (Marketplace display: **Kang's plugins**).
The publisher naming follow-up passed 30 focused tests and the real CLI install,
disable and uninstall smoke check. Add/search/update/delete used the same
record ID, checked actual stored state, and preserved a same-scope control record.
Native fixtures and handoff checks passed; native adoption remains unverified.
Embeddings in this run were the explicitly labeled local synthetic HTTP fixture.

The three new Codex Python scripts have 88% aggregate statement coverage in the
local full-suite report. SonarCloud and the hosted Windows command-resolution
fix require their current remote reruns; local coverage does not certify the
remote quality gate. npm lifecycle scripts are disabled, Python CI dependencies
use the existing hashed lock, and the builder permits only fixed Git operations
with a canonical directory passed through `cwd`, never as a CLI argument.

The cloud workflow preserves the plugin's fixed `requirements.txt`, then replaces
only Runtime with the immutable main SHA admitted by preflight (`--no-deps`) and
checks installed Git provenance. Its client pin includes these stronger checks.
The complete approved naming contract is recorded in `codex-naming.md`.

Publication is paused until the current PR commits pass their hosted checks,
SonarCloud findings are cleared, and CodeRabbit follow-up review completes.
Candidate builds, PR pushes and review-ready status do not authorize a release.
After acceptance, release the required Runtime first, update pinned MCP/plugin
dependencies and skill metadata, verify the released install, then publish the
Marketplace candidate. No new version, release tag or registry upload has been
performed during review remediation.

## NOT VERIFIED

- Real Codex subscription-account calls with CPU embeddings in one combined run.
  New local CPU model downloads were attempted three times; incomplete or timed
  out remote transfers failed closed. An older cached pipeline marker was also
  rejected rather than relabeled as compatible. Hosted fresh CPU tests passed
  independently as described above.
- Ollama Cloud model-driven CI execution. The lane must first reach reviewed
  upstream main and receive the existing environment's human approval. No
  subscription credential was copied to GitHub and no cloud pass is claimed.
- New-plugin Shared Owner end-to-end/model-driven multi-agent tests. The existing
  Runtime protected-owner security workflow passed for the adapter commit; that
  core evidence does not prove every new launcher configuration was exercised.
- Semantic deduplication of differently
  worded v1/v2 summaries, arbitrary future native formats, and complete sensitive
  personal-data classification. Current selection is by authorized home/version,
  explicit topic/category headings and fixed destination profile scope; sections
  and exclusions are reported. No project scope is inferred from untrusted text.
- Completely hash-locked transitive desktop runtime bundles and all public
  publisher assets/policies/demo materials. The development package pins direct
  distributions, Runtime Git source, skill snapshot and model identity.
- Final GitHub matrix results that remain queued/running are not represented as
  completed. Check each PR's current checks before merging.

## BLOCKED

- Plugin Creator account normalization: the private 0.1.1 candidate was created
  and saved successfully, then its actual files were read back. Creator generates
  `.mcp.json` and replaces the supplied legacy inline MCP overlay, omitting its
  `env_vars` allowlist. Deleting the generated file is explicitly rejected by the
  service. The GitHub/source ZIP preserves that tested overlay. Custom profile,
  executable, embedding-key and Shared Owner environment forwarding in the
  Creator-normalized variant is therefore blocked; its default CPU path is
  NOT VERIFIED. Do not transfer source/Marketplace test results to that variant.
  The private candidate is [available for inspection](https://chatgpt.com/plugins/plugins_6ae987f759d88191a320279bcd6404fd),
  while the repository Marketplace/source ZIP is the validated delivery path.

- Automatic native bulk writeback: no stable public plugin API was verified in
  the inspected Codex source/docs. Internal note handlers and SQLite/generated
  file edits are not substitutes. The CLI reports native import UNSUPPORTED.
- Desktop UI acceptance: the available Computer Use tool explicitly rejected
  control of `com.openai.codex` for safety reasons. No alternate UI mechanism was
  used to bypass that restriction. CLI evidence does not count as Desktop proof.
- Official public-directory release: local MCP submissions require approved
  partner allowlisting, verified publication identity and remaining preparation.
  The private Plugin Creator candidate is not a public-directory approval.

## DEFERRED

- P1 automatic recall/capture hooks and user-authorized extraction. Off by default;
  no hook is bundled, no Codex core modification simulates unsupported lifecycle.
- Additional native harness adapters when documented public interfaces and
  format fixtures are available. Generic readable JSON export remains available.

## Exit guarantee and remaining user actions

Verified exports remain readable and checksummable without installing the plugin.
Codex users can review them, enable native memories and request approved facts
through the actual client's supported remember interaction, then verify them in
a new chat. Any cloud/model processing of private exports needs prior approval.
The plugin cannot currently certify automatic native ingestion or consolidation.
Keep Qdrant until adoption is confirmed; disable/uninstall preserves all data.
AGENTS.md is project instruction and requires separate approval, never an implicit
native-memory import.

GitHub Marketplace candidate source/installability is implemented and locally
tested. Broad public release remains gated on current PR checks, reviewed Runtime
publication policy, Desktop evidence and the public-directory checklist. This
record distinguishes technical preparation from official review approval.
