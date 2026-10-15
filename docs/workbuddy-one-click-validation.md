# WorkBuddy managed installation release checklist

Status: **NOT VERIFIED for one-click installation**. This document describes
release acceptance for the proposed managed connector. The currently released
uvx connector is not evidence of a zero-environment installation.

## Current verification boundary

The existing MCP distribution suite passes 89 tests. The shared Runtime's
standalone suite passes 30 tests with its CLI and MCP dependencies installed.
Dependency compatibility checks pass in those environments. These results
verify existing behavior, not the proposed installer or real WorkBuddy GUI.
The complete Hermes host integration suite has not been rerun for this design.

Reproducible baseline commands, after installing the relevant development/test
dependencies and entry points in a virtual environment:

```sh
# In qdrant-memory-mcp
python -m pytest -q
uv pip check

# In hermes-plugin-qdrant-memory, installed with its mcp extra
python -m pytest -q tests/standalone
uv pip check
```

## Acceptance matrix

Run the entire lifecycle on a clean OS account or image without system Python,
uv/uvx, Node.js, Ollama or Qdrant Server. WorkBuddy-provisioned runtimes are
permitted. Hiding PATH alone does not establish a clean environment.

| Platform | Managed bootstrap | Local model | WorkBuddy GUI lifecycle |
| --- | --- | --- | --- |
| macOS Apple Silicon | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| macOS Intel | NOT VERIFIED | NOT VERIFIED; compatible ONNX wheel required | NOT VERIFIED |
| Windows x64 | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Linux x64 | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| Windows/Linux ARM64 | NOT VERIFIED; no support claim | NOT VERIFIED | NOT VERIFIED |

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
