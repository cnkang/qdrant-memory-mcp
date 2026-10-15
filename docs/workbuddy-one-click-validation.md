# WorkBuddy managed installation release checklist

Status: **NOT VERIFIED for one-click installation**. This document describes
release acceptance for the proposed managed connector. The currently released
uvx connector is not evidence of a zero-environment installation.

## Current verification boundary

The existing MCP distribution suite passes 89 tests. The shared Runtime source
adds optional CPU embedding and explicit profile setup. Its full host-backed
local regression run passes 407 tests with five explicit skips for separate
real-model/external-service acceptance. Real-model acceptance is run separately,
with no model download during ordinary test collection. Dependency compatibility,
Ruff and wheel/sdist builds pass locally. These results do not establish real
WorkBuddy GUI installation or a production managed launcher.

The [Runtime PR](https://github.com/cnkang/hermes-plugin-qdrant-memory/pull/48)
tracks native model/CLI/MCP acceptance. Final platform claims require terminal
CI results for the reviewed source; pending or superseded runs do not count.

Reproducible baseline commands, after installing the relevant development/test
dependencies and entry points in a virtual environment:

```sh
# In qdrant-memory-mcp
python -m pytest -q
uv pip check

# Optional managed-Python prerequisite, with Node.js 20+
node --test tests/test_managed_bootstrap.mjs
node integrations/managed/bootstrap.mjs --probe

# In hermes-plugin-qdrant-memory, installed with its mcp extra
python -m pytest -q tests/standalone
uv pip check
```

## Acceptance matrix

Run the entire lifecycle on a clean OS account or image without system Python,
uv/uvx, Node.js, Ollama or Qdrant Server. WorkBuddy-provisioned runtimes are
permitted. Hiding PATH alone does not establish a clean environment.

| Platform | Production managed bootstrap | Local model | WorkBuddy GUI lifecycle |
| --- | --- | --- | --- |
| macOS Apple Silicon | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| macOS Intel (best effort, not a release gate) | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Windows x64 | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Linux x64 | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Windows/Linux ARM64 | NOT VERIFIED; no support claim | NOT VERIFIED | NOT VERIFIED |

The macOS Apple Silicon command-line prerequisite probe verifies a fresh managed
Python with no system tools on PATH and managed-only interpreter selection.
Its observed runtime preparation was about 26 seconds on one run. A separate
fixed-artifact model experiment took about 175 seconds to prepare roughly
252 MB, then about 0.27 seconds to load offline. Ten synthetic bilingual query/
memory pairs ranked their corresponding record first in that small experiment.
These are measurements of distinct stages, not an end-to-end installation SLA.

For each supported platform, record OS and WorkBuddy versions, pinned package
and model versions, test command or GUI action, elapsed time, result and any
remaining limitation. Keep credentials, machine-specific paths, raw logs and
private operational records out of published documentation and packages.

| Required check | Acceptance | Current status |
| --- | --- | --- |
| Marketplace ZIP import | Correct metadata, icon, runtime declaration and canonical Skill | NOT VERIFIED for managed connector |
| Cold provisioning | Verified runtime/dependencies/model; no manual commands or admin rights | NOT IMPLEMENTED |
| MCP connection | Four tools available within actual client timeout; stdout is protocol-only | NOT IMPLEMENTED for managed bridge |
| Backend readiness | Separately confirmed setup and compatible collection | NOT IMPLEMENTED for managed setup |
| Local no-credential path | No Ollama, remote embedding or manual JSON/init required | NOT IMPLEMENTED |
| Cloud native form | URL/key mapping, authorized new collection, valid and invalid credentials | NOT IMPLEMENTED |
| Retrieval | Save ten synthetic Chinese/English memories and verify expected recall | NOT VERIFIED with candidate local model |
| Exact modification | Update/delete by returned ID; reject inaccessible/nonexistent IDs safely | NOT VERIFIED through managed connector |
| Restart | Exit WorkBuddy completely; reconnect and recover the same records | NOT VERIFIED through managed connector |
| Crash/retry | Kill backend or interrupt each provisioning stage; retry without duplicate records | NOT VERIFIED |
| Isolation/ownership | Independent profiles/scopes; concurrent WriterLease rejected | NOT VERIFIED through managed connector |
| Collection mismatch | Wrong dimension/fingerprint/identity fails without deletion or replacement | NOT VERIFIED through managed connector |
| Upgrade/rollback | Preserve data and ledger; incompatible downgrade fails safely | NOT VERIFIED |
| Supply chain | Pinned artifacts/hashes; no unchecked installers or executable partial downloads | NOT IMPLEMENTED for managed installer |
| Extraction safety | Reject traversal, archive links and destination symlink escapes | NOT IMPLEMENTED for managed installer |
| Secret handling | No keys in argv/logs/files; no service keys inherited by installers | NOT VERIFIED for managed connector |
| Untrusted memories | Retrieved text remains data; no instruction or permission escalation | NOT VERIFIED through managed connector |
| Existing clients | Full Hermes, Python MCP and relevant client regression suites pass | NOT VERIFIED for proposed changes |

Measure cold installation, dependency download, model download, initialization,
warm MCP connection and ordinary tool latency separately. Do not merge cold
download time into a warm-start measurement or call CLI simulation GUI acceptance.

## WorkBuddy confirmation and release gates

The [official specification](https://open.workbuddy.cn/docs/connector) establishes
configuration syntax and documented timeouts. Still verify actual client
behavior for asynchronous backend preparation, connection recovery, process
termination, CLI no-auth installation, update/rollback and credential removal.
There is no verified generic MCP provisioning hook in this design.

Production architecture selection remains **BLOCKED on cold-start and platform
validation**. Marketplace submission readiness and the complete one-click P0
acceptance remain **NOT VERIFIED**. Do not publish either claim from passing
baseline tests alone.
