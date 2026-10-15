# Managed Python prerequisite probe

This is a reproducible installation experiment for Node-based clients. It is
**not a production WorkBuddy launcher** and is not referenced by the marketplace
connector configuration. It neither downloads an embedding model nor creates
a profile, collection or ledger.

With Node.js 20 or newer:

```sh
node --test tests/test_managed_bootstrap.mjs
node integrations/managed/bootstrap.mjs --probe
```

The explicit `--probe` downloads a fixed official uv wheel, checks its exact
byte length and SHA-256, extracts only the exact regular executable into a fresh
private directory, and asks uv to prepare Python 3.11.15. It does not execute a
remote installer script, invoke an archive utility or require a system Python,
uv/uvx installation, administrator rights or service credentials. uv's managed
Python mechanism uses its pinned python-build-standalone metadata.

The child processes receive a deliberately restricted environment with an empty
PATH, private uv/Python cache/install directories and managed-only Python
selection. The probe checks that the executed Python belongs to that fresh
directory. This remains a command-line prerequisite test on an existing OS,
not a clean WorkBuddy GUI marketplace installation.

Only a fully verified bootstrap executable can run. ZIP paths are never used as
filesystem destinations; symlink, encrypted and unsafe path entries are refused.
Temporary probe files are retained for explicit inspection/removal and are
separate from all memory data. Service credentials are not passed to uv/Python.
The probe needs access to PyPI and Python distribution download endpoints.

CI exercises Linux x64, Windows x64 and macOS Apple Silicon. A macOS Intel
artifact is included for best-effort experiments only; Intel is not a formal
support or release gate. Other architectures have no support claim here.

Passing this probe establishes only the runtime prerequisite. Python package
installation, explicit embedding-provider selection, backend initialization,
MCP startup within client time limits, restart/upgrade and WorkBuddy GUI
acceptance are separate requirements. In particular, first-time runtime/model
downloads must not block a 30-second MCP handshake. See the
[managed installation design](../../docs/workbuddy-one-click-architecture.md).
