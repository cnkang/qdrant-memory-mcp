# WorkBuddy managed installation release checklist

Status: **NOT VERIFIED for one-click installation**. This document describes
release acceptance for the proposed managed connector. The currently released
uvx connector is not evidence of a zero-environment installation.

## Current verification boundary

The existing MCP distribution suite passes 89 tests. The shared Runtime source
adds optional CPU embedding and explicit profile setup. Its full host-backed
local regression passes 428 tests with six explicit skips for separate
real-model/external-service acceptance. Real-model acceptance is run separately,
with no model download during ordinary test collection. Dependency compatibility,
Ruff and wheel/sdist builds pass locally. These results do not establish real
WorkBuddy managed installation or a production managed launcher. A separate
manual CPU GUI acceptance is described below.

The [Runtime PR](https://github.com/cnkang/hermes-plugin-qdrant-memory/pull/48)
tracks native model/CLI/MCP acceptance. Final platform claims require terminal
CI results for the reviewed source; pending or superseded runs do not count.
The optional CPU-model jobs passed on Linux x64, Windows x64 and macOS Apple
Silicon for Runtime commit `26f13eb1f84b0c44d442c13642da30049d19753c`.
The managed-Python prerequisite jobs passed on the same platforms for MCP commit
`23aa071229bedbcb957c3e2037aa06c4d3f99f92`. These are source-candidate results;
neither feature is available in the current published connector.

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

| Platform | Node prerequisite probe | Optional CPU Runtime acceptance | Manual CPU WorkBuddy GUI |
| --- | --- | --- | --- |
| macOS Apple Silicon | PASS in native CI | PASS in native CI | PASS for the lifecycle below |
| macOS Intel (best effort, not a release gate) | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Windows x64 | PASS in native CI | PASS in native CI | NOT VERIFIED |
| Linux x64 | PASS in native CI | PASS in native CI | NOT VERIFIED |
| Windows/Linux ARM64 | NOT VERIFIED; no support claim | NOT VERIFIED | NOT VERIFIED |

A production managed connector remains **NOT IMPLEMENTED** on every platform.

The macOS Apple Silicon command-line prerequisite probe verifies a fresh managed
Python with no system tools on PATH and managed-only interpreter selection.
Its observed runtime preparation was about 26 seconds on one run. A separate
fixed-artifact model experiment took about 175 seconds to prepare roughly
252 MB, then about 0.27 seconds to load offline. Ten synthetic bilingual query/
memory pairs ranked their corresponding record first in that small experiment.
These are measurements of distinct stages, not an end-to-end installation SLA.

A separate command-line cold-chain experiment on Apple Silicon used a newly
provisioned managed Python, a fresh dependency environment and an empty model
cache, with system tools removed from PATH and managed-only Python selection.
Runtime preparation took about 87 seconds, dependency installation 116 seconds,
explicit CPU setup/model preparation 258 seconds, and offline real-MCP acceptance
11 seconds. This proves the components can run together without Ollama, but is
not a WorkBuddy installation test or a clean-OS certification. The cold chain
exceeds both a normal MCP connection timeout and a five-minute installation
budget; a production connector still needs a verified staged preparation flow.

### Manual CPU GUI acceptance

WorkBuddy 5.8.2 on macOS Apple Silicon was tested with a pre-provisioned source
candidate, a verified CPU-model cache and a newly initialized, isolated embedded
profile. Its packaged Runtime code matches commit
`09ba437b79274f4f31e554a8dbc2dc3eb1ee484e`. Python provisioning and profile setup happened outside WorkBuddy;
the custom MCP configuration was entered manually. This is not marketplace
installation, an automatic setup test or a clean-OS certification.

The GUI showed a connected server with all four tools enabled. It saved ten
synthetic Chinese/English memories, and three searches returned their expected
record first. Updating one returned ID preserved its identity and changed its
text; deleting another exact ID removed it from subsequent search results.
After a confirmed complete WorkBuddy exit, backend diagnostics reported nine
stored records and twelve committed operations (ten adds, one update, one
delete). After relaunch, three real GUI searches confirmed the updated record,
an unchanged English record and continued absence of the deleted ID.

The tested source candidate uses the shared Python Runtime's optional CPU
provider. This result does not validate a Node bridge, connector ZIP import,
automatic provisioning, Cloud credentials, upgrade/rollback or other platforms'
GUI lifecycle. No screenshots, account data, private paths or raw logs are part
of this report.

### Managed-connector acceptance

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
| Retrieval | Save ten synthetic Chinese/English memories and verify expected recall | PASS for manual CPU GUI (three queries); managed path NOT IMPLEMENTED |
| Exact modification | Update/delete by returned ID; reject inaccessible/nonexistent IDs safely | Update/delete PASS for manual CPU GUI; managed path NOT IMPLEMENTED; ID rejection covered separately by Runtime tests |
| Restart | Exit WorkBuddy completely; reconnect and recover the same records | PASS for manual CPU GUI; managed path NOT IMPLEMENTED |
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

Production architecture selection remains **BLOCKED on staged cold-start and
WorkBuddy lifecycle validation**. Marketplace submission readiness and the complete one-click P0
acceptance remain **NOT VERIFIED**. Do not publish either claim from passing
baseline tests alone.
