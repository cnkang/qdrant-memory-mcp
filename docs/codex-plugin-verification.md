# Qdrant Memory for Codex: engineering and acceptance record

## Latest status update (2026-11-13)

The public plugin remains **0.1.3**. A 0.1.4 source candidate is being prepared
against MCP 0.3.3, Runtime 0.6.2 and the pinned Skill 0.4.2 snapshot; it is not
published. A fresh Python 3.11 environment installed MCP 0.3.3 and Runtime
0.6.2 from public PyPI and passed `uv pip check`; the final clean 0.1.4 ZIP,
protected Cloud acceptance, and Creator readback are still pending.
MCP 0.3.3 passed its exact-main release gate at
`7571bc73a4cdd8d5059ba6cc4664b1837ee02566` and is published on public PyPI and
the MCP Registry. A fresh public-PyPI install was verified; the GitHub Release
`v0.3.3` remains a draft with the WorkBuddy connector artifacts.

The user manually verified the 0.1.3 setup and tool flow in Codex Desktop,
including setup in an isolated profile and subsequent memory operations. That
evidence applies to 0.1.3 only. The 0.1.4 candidate still needs its own Desktop
acceptance; it must not inherit the earlier result.

The Codex CI workflow keeps its required package, merged-package and lifecycle
lanes fixed at Node 22, Python 3.11 and Codex CLI 0.167.2. Optional manual
inputs select Node 22/24, Python 3.11/3.14 and Codex CLI 0.167.2/0.165.0 only
for a separate compatibility probe. The selected values are validated against
those choices and the CLI is installed from checked-in integrity-locked files.
Protected Cloud acceptance remains fixed. Product, Runtime, MCP, Skill, action
SHA and dependency-lock pins remain source-controlled release inputs.

Plugin Creator currently serves the private 0.1.1 release; its normalized
`.mcp.json` has an empty environment map. The eight Codex environment names
have not been verified in a Creator-normalized candidate.

## Candidate verification run (2026-11-09, codex/plugin-readiness-20261109)

Environment: macOS 27.2 Apple Silicon (arm64), Codex CLI 0.165.0, Node 24.18.0,
Python 3.11.15 (uv venv, hash-locked `.github/requirements-sonar-ci.txt`),
MCP SDK 2.3.0, MCP distribution 0.3.1, Runtime 0.6.0 at the pinned commit
`dee6777432f17523db75f6be32cf3ef15e48235c`, Skill 0.4.1 at
`8f6e5280559f7f1d5e04781c6910b8c33b5f2dae`, uv 0.13.6. The run works in an
isolated `CODEX_HOME` and a work directory outside both repositories; the DSH
worktree (`/Volumes/2T/development/qdrant-memory-mcp`, branch
`codex/dsh-native-v1`) was read-only from here.

### New credential-free real-CLI E2E lane

`scripts/codex_plugin_e2e.py` (new) drives the actual installed Codex CLI
without any subscription. Executed run (canonical evidence JSON:
`docs/evidence/codex-e2e-20261109.json`, reproducible in CI as workflow job
`lifecycle-e2e`):

| Step | Result |
|---|---|
| `plugin marketplace add` + `plugin add qdrant-memory@cnkang` from the repository marketplace | PASS, version 0.1.3, installed cache carries `.codex-plugin/plugin.json` overlay and setup skill |
| `codex mcp get qdrant-memory` | all **eight** overlay environment names visible through the CLI (values masked by CLI) |
| uninstall + marketplace cleanup | PASS (cache removed) |
| build source ZIP from the exact commit with the pinned Skill snapshot | PASS (`build()` byte-for-byte archive path, SHA-256 recorded in the JSON evidence) |
| install from the exact rebuilt ZIP through a temp ZIP marketplace | PASS, same identity/version and all eight env names |
| Runtime install from the installed plugin's pinned `requirements.txt` into a private venv | PASS (uv venv 3.11 + pip, includes Git-pinned runtime build) |
| `node launcher.mjs doctor` | exit 0 |
| MCP SDK session through the real launcher | initialize + exact four tools `qdrant_memory_{search,add,update,delete}` |
| duplicate `add` of an identical fact | **idempotent: same record ID returned** |
| exact-ID `update` then exact-ID `delete` | correct IDs; neighborhood scope unchanged (inventory) |
| fresh-session persistence (new client process) | PASS |
| hard `SIGKILL` of the launcher mid-session after a real initialize, then a new session | data intact (exit signal −9 observed; recovery PASS) |
| sibling profile isolation | zero leaking records in the E2E lane |
| cross-profile exact-ID `delete` | rejected as an MCP error in the regression suite (`tests/test_codex_plugin.py`), not in the E2E lane |
| disable via `config.toml`, `plugin remove`, marketplace removal | PASS; uninstall never deleted data |
| post-uninstall data retention | the Runtime binary alone still serves the record over stdio MCP ("uninstall_preserved_record") |

Notes: no production memory was touched; embeddings were the deterministic
local HTTP fixture (`synthetic-fixture`, 3 dimensions) consistent with the
protected acceptance harness; the CPU-model path is unchanged from the
2026-11-06 evidence (first download 507.59 s, offline inference verified).
This lane does not substitute for Desktop GUI acceptance or Plugin Creator
evidence, and it does not invoke the four tools through a Codex model
conversation — that remains the protected lane's evidence.

Reproducibility of the new source archive on this host: two consecutive
`build_codex_plugin.py` runs on this branch produced byte-identical archives
(compared on disk), and the executed E2E's ZIP build record — including its
SHA-256 — is in `docs/evidence/codex-e2e-20261109.json`. Every later commit
needs its own exact-SHA three-OS runs, as before.

### Regression coverage added

`tests/test_codex_plugin.py` now covers 25 cases (was 23): a launcher failure
injection where the runtime venv lacks the pinned MCP distribution (fails
closed before any write), plus a real-MCP scope-isolation suite with a sibling
profile (zero leakage, cross-profile exact-ID delete rejected as an error,
control record preserved). Local run: **25 passed**. Release gate
(`scripts/check_release_gate.py`) now requires the "Codex plugin" workflow for
tagged commits; `tests/test_release_gate.py` updated.

### Plugin Creator / env forwarding recheck against the released spec

Released [Agent Plugins MCP schema 1.0.0](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json)
still declares only `type|command|args|cwd|env` for stdio servers and has **no
`env_vars` field**; the Codex overlay's `env_vars` remains the working
Codex-specific passthrough and the CLI demonstrably surfaces all eight names
(above). The submission portal "derives `.mcp.json` and
`.codex-plugin/plugin.json` from root `plugin.json` and `mcp.json`" for
portable packages, which matches the recorded 0.1.1 Creator normalization
(`env: {}`). The current private Creator release still reads back with `env: {}`;
no Creator-side evidence shows the eight names survive normalization for the
0.1.4 candidate. Creator-normalized forwarding stays **NOT VERIFIED**. The
0.1.3 repository Marketplace/source ZIP remains the validated delivery path;
the 0.1.4 source candidate still requires its own package and install evidence.

### Hooks research conclusion (drives Mode B separation)

Released docs confirm plugin-bundled lifecycle hooks exist, load only for
**manually installed** Codex desktop plugins, are skipped until trusted per
definition hash, and **"aren't eligible for the public plugin directory"**;
"Remove lifecycle hooks before public directory submission."
[Build plugins](https://developers.openai.com/plugins/build/plugins);
[Submission](https://developers.openai.com/plugins/deploy/submission);
[Codex hooks](https://learn.chatgpt.com/docs/hooks). Detailed matrix:
`docs/codex-native-lifecycle-capability-matrix.md`.

Mode A (this plugin) keeps zero hooks. Mode B ships as a separate,
clearly labeled preview under `integrations/codex-lifecycle/` with:
`SessionStart` recall via `hookSpecificOutput.additionalContext` and
`UserPromptSubmit` explicit `remember:` directive capture (no model, no
extraction, verbatim text only). Real-CLI verification on 0.165.0: the preview
marketplace installed the hooks plugin (`qdrant-memory-lifecycle@cnkang-lifecycle-preview`),
`codex mcp list` stayed untouched (the preview declares no server), and
remove/cleanup passed. **Hook registration and firing in a real session were
not observed on 0.165.0**; the manifest install alone is not evidence that the
file-backed declarations register. Handler units
(`tests/test_codex_lifecycle_hooks.py`, 18 cases) verify the released output
contract, size limits, scope enforcement and failure surfacing. **A real
trust-reviewed Codex session firing both hooks is NOT VERIFIED** (needs a
subscribed, hook-enabled client session); `Stop`-based automatic capture is
NOT IMPLEMENTED by design. Guard tests assert the public package contains no
hooks (`test_main_plugin_package_contains_no_hooks`).

### Desktop-only dependency locks (prototype, still NO-GO)

`scripts/build_runtime_locks.py` (new) produced `runtime-locks/*.txt` for
`linux-x64`, `macos-arm64`, `macos-x64`, `windows-x64` — hash-locked,
binary-only transitive resolutions of the plugin's pinned requirements (62
pinned wheels for `macos-arm64`; 58 for `linux-x64`), plus the Runtime wheel
built from the pinned commit with its SHA-256 recorded in
`runtime-wheel.json` (the wheel build is not byte-reproducible; the SHA pins
the recorded artifact). Offline acceptance on this host:

```text
pip download (hashes, binary-only) → 64 wheels, 64 MB
venv + ensurepip + pip install --require-hashes --only-binary=:all: \
       --no-index --no-cache-dir --find-links wheelhouse \
       -r verify-macos-arm64.txt   → PASS, console probe OK (qdrant-memory --help)
```

`--verify` now refuses a target whose architecture differs from the host. The
lock files carry the universal hash set, so an arm64 host selecting arm64
wheels does not prove an x64 install. A macOS x64 pass is therefore **NOT
VERIFIED**: it needs an Intel host, and `cryptography==50.0.2` publishes no
macOS x86_64 wheel, so the binary-only requirement cannot be satisfied for
that target until the dependency set changes. The earlier "same for
macos-x64 → PASS" observation is withdrawn: it was produced on an arm64 host.

Windows and Ubuntu offline installs remain **NOT VERIFIED here** (resolved
locks exist; runner-proof pending). This does NOT complete a Desktop-only
package: bundle layout, per-platform archive selection, SBOM, license
aggregation, clean-Desktop launch route, and the CPU model delivery decision
are unchanged blockers. See `docs/desktop-only-adr.md` (NO-GO).

### DSH parallel-work compatibility analysis (PR #81, `codex/dsh-native-v1`)

Read-only: `git diff origin/main...codex/dsh-native-v1` touches
`integrations/dsh/**`, DSH workflows/scripts/tests, plus README/CHANGELOG and
a one-line `scripts/check_release_gate.py` change (adds "DSH native adapter"
to `REQUIRED_WORKFLOWS`). It does **not** change `plugins/`, the marketplace
manifest, or `tests/test_codex_plugin.py`. This branch adds "Codex plugin" to
the same tuple — one adjacent-line merge conflict, trivially resolvable --
and no other shared file. Runtime pin: DSH consumes Runtime 0.6.1-era
interfaces for native lifecycle work; this Codex branch keeps the published
Runtime 0.6.0 pin and requires **no** Runtime upgrade (verified by the E2E
above against 0.6.0). Runtime issue [#115](https://github.com/cnkang/hermes-plugin-qdrant-memory/issues/115)
recheck: OPEN as of 2026-11-05 update — Windows `windows-latest` CPython 3.14.7
probes stored 100/100 events, full suite passed, no recurrence within timeout;
the issue is kept open expressly pending #118's interpreter comparison, with
writer-drain diagnostics retained before any retry policy change. The Codex
launcher/CLI path here never exercised the drained-writer failure path, so
PROJ-05 stays NOT VERIFIED rather than PASS.

### Current gate

The 2026-11-06 gate remains; refreshed items (E2E lane, env-forwarding
evidence, locks prototype, hooks preview, release-gate addition) are recorded
above. Desktop-only stays **NO-GO**. Public-directory status stays
NOT_SUBMITTED. No publish, tag, registry upload or Creator overwrite occurred.


## Current repository-marketplace candidate (2026-11-06)

Plugin 0.1.3 pins MCP 0.3.1, Runtime 0.6.0 at
`dee6777432f17523db75f6be32cf3ef15e48235c`, and `qdrant-memory` Skill 0.4.1
at merged Skills main commit `8f6e5280559f7f1d5e04781c6910b8c33b5f2dae`,
which includes the merged PR #54 operator workflows, PR #56 clarifications,
PR #57's handoff export path fix, and PR #58's Codex profile and model identity
clarifications.
The tracked marketplace plugin
includes the complete 21-file Skill snapshot; the archive builder compares it
with the pinned commit and rejects drift. An earlier local 0.1.3 source
Marketplace ZIP was built from commit `0ae3a0e5434c6feb19773e1990d6bd60a5d151e9` (34 files,
77,872 bytes, SHA-256
`824295e83ee833abdc29e5512d24893fedcf63c1df96f4ad97834fb6821d7072`). Codex
CLI 0.165.0 installed that exact ZIP through an isolated temporary Marketplace;
version 0.1.3 was visible, disable and uninstall passed, and the ZIP remained.
This did not invoke the four memory tools through a Codex CLI conversation.
The evidence below for plugin 0.1.2 remains historical.

## Desktop-only engineering update (2026-11-06)

This repository-marketplace candidate is still not a complete Desktop-only
archive. `docs/desktop-only-adr.md` records the proposed bundle direction;
`docs/desktop-only-requirements-traceability.md` records official MUST/SHOULD,
project gates and platform blockers. The current plugin ZIP builder continues
to build the source Marketplace form only.

The previous 0.1.2 snapshot used Skill 0.4.0. The 0.1.3 candidate includes the
operator workflows from merged Skills PR #54 and clarifications from merged
PR #56, then pins their merged main commit. The first CI run used the former
Skill checkout pin and failed before
producing an artifact. The corrected exact-SHA source workflow
[42069609457](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42069609457)
passed on Ubuntu, macOS and Windows. However, the Windows ZIP differed from the
Ubuntu/macOS ZIP because 32 text files were checked out with CRLF. The two
non-Windows archives were identical (77,870 bytes,
`4527e53da8eb0e1f6b234e95e7759b9001069508511d19509f98dd655165b55c`); the
Windows archive was 78,705 bytes with SHA-256
`e3eca41e6796415cfbe100c92e8a34fef1a210bd0b998507afdf58b371f217fc`.
The builder normalizes known UTF-8 text from tracked plugin files and the pinned
Skills archive to LF before comparison and packaging. Binary files are left
untouched, the regression test covers CRLF and bare-CR input, and failed
snapshot comparisons list differing paths. On commit
`91a8d252920bc5ef469ef0cd78f29b145ce6f2fb`, exact-SHA CI
[42077121065](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42077121065)
passed all three OS jobs. The Mac/Linux artifacts had SHA-256
`32af08c53f31da9704dbd1e30dc1969d5c424acc22989489112df280df3fdf44`; Windows
had `5ddc69aaaced9602210f4ed727636c14c377c2efaaded697eb88eae6f1ad2fa8`. All
34 uncompressed file payloads and ZIP metadata matched; only the DEFLATE byte
streams differed by host zlib. Commit
`d26873b4bf34f21f3e2e7691f1f3e283c181c863` switched to ZIP_STORED. Its exact-SHA
run [42078522937](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42078522937)
passed the Ubuntu and Windows package jobs; the macOS job was still queued when
inspected. The available 177,573-byte artifacts had different SHA-256 values
(Ubuntu `b20c7871b38ce7440131a3be45e3e286fbd5fb282e83fdc533f7e3e1d7685e4e`,
Windows `f3311b2910891cc2f1b733c687fc97c94f520f7c9b1c5c6083c0ccc387b1a706`),
although the payloads and all compared entry metadata matched. The remaining
difference is the ZIP creator-system marker (Unix 3 versus DOS 0); the builder
now pins it to Unix 3 and the regression test checks that value. On the exact-
SHA commit `ada8c470cc0ba9616c97eb60da6a8fa2be98266b`, run
[42083465459](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42083465459)
passed Windows, macOS and Linux and produced identical 178,139-byte, 34-file
source archives with SHA-256
`284626b0db2505562af324dd62ce3f460948b137cf98202c5f85d3c273d9b7e2`; the
matching local clean build confirmed the same hash. Any later commit requires
its own exact-SHA verification. A prior pre-commit
`linux/amd64` container run (Node 22.23.4, Python 3.11.17) passed
`tests/test_codex_plugin.py` → **22 passed**; it predates ZIP_STORED and the
creator-system marker fix. None of these source ZIP checks certify a
Desktop-only package.

On 2026-11-06, Codex CLI `0.165.0` installed the local source Marketplace into
an isolated `CODEX_HOME` using `codex plugin marketplace add` and
`codex plugin add qdrant-memory@cnkang`. `codex mcp list/get` showed the local
stdio server and the eight declared overlay environment-variable names, with
values masked. This confirms the Codex CLI source-install path, not Plugin
Creator normalization or a Desktop GUI run.

The real MCP SDK source-entrypoint test was rerun with MCP SDK 2.3.0, MCP
distribution 0.3.1 and Runtime 0.6.0 at the pinned release commit. Command:
`/private/tmp/qdrant-ci-py311-uv-copies/bin/python -m pytest -q tests/test_codex_plugin.py`;
result: **20 passed in 2.34s**. It includes real MCP initialize, exact four-tool
discovery and synthetic add/search through the Node launcher. It is not evidence
for the missing bundled Python/runtime dependencies in a Desktop-only ZIP.

Runtime PR [#127](https://github.com/cnkang/hermes-plugin-qdrant-memory/pull/127)
merged at `b05143da0311d956d8479024d2aeff8253dfb907` and fixes selection of the
interpreter used to build each managed test environment. Its exact-SHA CI run
[42159067998](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/42159067998)
passed the Python 3.11/3.14 behavior and host-compatibility jobs, MCP protocol
coverage, SonarCloud, and the required security gate. Runtime issue #118 remains
open in GitHub even though its fix is merged and verified. Runtime issue #115
also remains open; no root cause or full failure-path recovery proof is
established.

## Embedding and model acceptance (2026-11-06)

Runtime 0.6.0's default CPU model was confirmed from `qdrant_memory/local_model.py`:
FastEmbed 0.9.1, model
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, Qdrant artifact
revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`, 384 dimensions. The actual
first online download and pinned size/hash validation took **507.59 seconds**.
An offline cached inference run with Hugging Face offline flags enabled and
HTTP(S) proxies pointed at `127.0.0.1:9` returned a finite 384-dimensional
vector. Runtime tests:

```text
/tmp/qdrant-ci-py311/bin/python -m pytest -q tests/test_local_model.py tests/test_local_embedding.py
37 passed in 3.09s
```

Model artifact provenance from the pinned revision:

| File | Bytes | SHA-256 |
|---|---:|---|
| `model_optimized.onnx` | 235052644 | `634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99` |
| `tokenizer.json` | 17083009 | `fa685fc160bbdbab64058d4fc91b60e62d207e8dc60b9af5c002c5ab946ded00` |
| `config.json` | 673 | `c8ec081fdad2df991bf5abbf18418fec7a5cdaa421f60ffb060a30040b8c376f` |
| `special_tokens_map.json` | 964 | `8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835` |
| `tokenizer_config.json` | 1416 | `0666eebf692422757e1dddf3c9fb1ded73ba3dc726c5828671fc89e45bf3609f` |

Total expected model download: **252138706 bytes**. These weights were cached
outside the plugin archive. Whether Desktop-only review accepts a user-approved
model download remains **unconfirmed**.

Ollama **0.40.14** and the already installed local model `qwen3-embedding:4b`
were exercised through Runtime's actual `HTTPEmbeddingProvider` at
`http://127.0.0.1:11434`; it returned a finite **2560-dimensional** vector.
No Ollama model was downloaded for this test. The isolated script neutralized
the host-only secret resolver because the `agent.secret_scope` host module is
not installed in this environment; the loopback endpoint used no credentials.
OpenAI-compatible protocol test
command:

```text
/tmp/qdrant-ci-py311/bin/python -m pytest -q tests/test_config_embedding.py -k embedding_wire_contract
2 passed, 17 deselected in 0.02s
```

That test uses `httpx.MockTransport`, verifies the `/v1/embeddings` request and
response contract, and does not constitute a live external provider test. No
API key or external embedding service was used. Runtime issue #115's writer
drain failure-path tests, low-disk model behavior and unsupported CPU case
remain **NOT VERIFIED**.

## Codex memory migration regression (2026-11-06)

On Runtime branch commit `4ca2950f0bfac20cd7e10081320c207b90fdbc16`, the
isolated Python 3.11.15 command

```text
/tmp/qdrant-ci-py311/bin/python -m pytest -q tests/test_codex_memory.py -k 'not test_cli_confirmed_import_and_handoff_use_real_profile and not test_handoff_tilde_profile_checks_actual_recovery_ledger and not test_deleted_import_reports_conflict_without_verify'
```

returned **64 passed, 4 deselected**. The selected cases exercise supported
semantic layouts, dry-run zero writes, de-duplication, durable import resume,
handoff checksums and path-race protections. The four deselected CLI/profile
cases require the Hermes host's top-level `utils` module, which is not installed
in this isolated Runtime venv. `tests/test_inventory_export.py` also could not
collect locally because `agent.memory_provider` was unavailable. The
Windows-only file tests were skipped on macOS; the exact Runtime CI run's
Windows security jobs passed on Python 3.11 and 3.14. This is not a full
Desktop migration or post-uninstall test.

## MCP distribution suite

Before running the full MCP suite, stale ignored 0.3.0 wheel and sdist artifacts
were moved to `/private/tmp/qdrant-mcp-stale-dist-backup/`; current 0.3.1 artifacts
were rebuilt with `uv build --out-dir dist`. Then
`/private/tmp/qdrant-ci-py311-uv-copies/bin/python -m pytest -q` returned
**297 passed, 2 skipped in 45.62s**. The separate Desktop-only runtime bundle
and its SBOM are still absent.

Codex Desktop and ChatGPT Desktop remain **NOT VERIFIED**. The authorized UI
session found the Mac locked. Creator-normalized configuration was not tested;
no Creator archive validator is available without creating or uploading a
plugin, which is out of scope. No Desktop-only ZIP, SBOM or public submission
was produced.

Local Codex CLI 0.165.0 subscription acceptance passed for the 0.1.2 candidate:
add/search/update/delete were called against the plugin, imported fixture state
and handoff contents were verified, and uninstall preserved data. A GitHub source
marketplace branch smoke check also installed 0.1.2. These local checks
used the repository source. Protected cloud acceptance validates both the
repository-backed marketplace source and the exact ZIP built from the same
merged `main` commit. Both installations must pass; the combined result also
checks the accepted ZIP SHA-256 against its build metadata. The result artifact
retains both acceptance records, while a separate artifact retains the ZIP and
build metadata. The historical 0.1.1 evidence below does not certify 0.1.2.

The Codex source marketplace is the public `cnkang/qdrant-memory-mcp` repository;
its display name is **Kang's plugins** and the install selector is
`qdrant-memory@cnkang`. The npm launcher 0.1.0-rc.8 is public, its registry
integrity matches `launcher-source.json`, and both `latest` and `next` point to
rc.8. This Codex plugin uses its bundled local launcher and does not depend on
the managed npm launcher.

The OpenAI public directory is a separate submission. The Plugin Creator copy
is a private USER-scoped 0.1.1 plugin and was inspected read-only. Its stored
`plugin.json` references a Creator-normalized `.mcp.json` whose server has
`env: {}`; the source Codex overlay instead declares eight `env_vars` names for
Profile, Qdrant/Embedding credentials, executable paths and Shared Owner
configuration. This confirms a manifest-shape mismatch in the existing 0.1.1
Creator copy. No Creator-normalized 0.1.3 archive was generated or executed, and
no claim is made that the mismatch is resolved. The 0.1.1 file inspection is
not a current-candidate or Desktop GUI test. The local stdio package has not
been submitted to the public directory.

## Historical 0.1.1 verification record

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
This workflow runs its Codex acceptance once from the repository marketplace
catalog and again from the exact rebuilt ZIP; neither installation path stands
in for the other, and the release result passes only if both pass and the ZIP
SHA-256 matches its build metadata.

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
- Ollama Cloud acceptance with the final release pins. Protected run
  `41768867472` passed at source `2da4ec66255467e28867b589e2b61895d0debe16`
  with `deepseek-v4.1-flash`, but that source predates these release pins.
  Repeat the protected acceptance after the pins change. This CLI run does not
  establish native support or Desktop UI acceptance.
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
- Desktop UI acceptance for plugin 0.1.4: the user's manual Codex Desktop test
  verified the earlier public 0.1.3 setup and tool flow. It does not verify this
  newer candidate, which still needs a fresh Desktop install and acceptance run.
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
