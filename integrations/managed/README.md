# Managed Qdrant Memory launcher (source candidate)

The shared launcher prepares Python, installs the pinned Runtime candidate and
prepares a verified CPU model. WorkBuddy and DSH use separate memory profiles.
Existing Hermes and standalone installations are unchanged. Node.js 20+ is the
only preinstalled language runtime needed for this candidate.

```sh
# DSH: complete preparation before enabling its MCP overlay.
node integrations/managed/launcher.mjs prepare dsh
node integrations/managed/launcher.mjs mcp dsh

# WorkBuddy: the source preview can prepare after a prompt MCP handshake.
node integrations/managed/launcher.mjs mcp workbuddy --auto-setup
```

For WorkBuddy, adapt the absolute launcher path in
[`mcp.managed-preview.json`](../workbuddy/mcp.managed-preview.json) and use a
custom MCP connection. Installing this explicit auto-setup connection authorizes
downloads and creation of its new private profile. The preview requests the
host's managed Node runtime but is **not a marketplace one-click release**.
No npm package has been published. `package.json` is deliberately private.
The original published Python connector remains available separately.

The four tools appear immediately. During preparation they return an error
stating no operation occurred. Wait for preparation before asking the agent to
save a fact. Writes are never queued. Backend confirmation is the only evidence
of a successful operation. Install failures return a bounded, sanitized error.
Use `prepare workbuddy` or `prepare dsh` to retry explicitly, then reconnect a
connection that has already reported preparation failure. For an interrupted
write, check the exact operation and its ID before any repeat. Do not repeat an
uncertain write unless a repeat is safe for that operation.

Program versions and model files are shared read-only after preparation. Each
host owns a separate profile. See [paths and versions](../../docs/cross-harness-architecture.md).
The installer refuses symlink paths, changed/unowned profiles and concurrent
provisioning. It never resets storage, overwrites another host's settings or
steals a WriterLease. Normal failed preparation releases its provisioning lock.
An orderly client probe interruption can resume the same partial Python
environment on the next preparation attempt. Its files are retained and checked.
If a force-killed installer leaves `.provision.lock` or `uv.pending`, first
confirm that its process tree is gone, then inspect/remove only that installation
transaction's stale file/directory. Do not remove Runtime data locks or profile
files. This crash-recovery procedure is operator-only, not automatic lock theft.

The candidate verifies bootstrap and Runtime archive bytes before execution.
Runtime verifies model artifacts. Python dependencies and build tools are pinned
with artifact hashes. Production publication and platform/host acceptance remain gated.
Installer subprocesses receive a restricted environment without service keys.
The server receives configured host credentials only through its environment.
Raw child stderr is never copied to MCP stdout or install diagnostics.

On disconnect the launcher aborts preparation and closes the backend's stdin,
allowing normal storage/lease cleanup before timed termination. A backend exit
closes the bridge so host reconnect policy can act. No write is automatically
replayed. Disable the connection before upgrades or CLI maintenance. Program
versions live beside each other. Data is never erased on upgrade, disconnect or
uninstall. Rollback compatibility is enforced by Runtime and must be validated
before a production upgrade is offered.

Run local safety and lifecycle tests:

```sh
node --test tests/test_managed_bootstrap.mjs tests/test_managed_launcher.mjs
python3 -m pytest -q tests/test_managed_bridge.py tests/test_cross_harness.py
```

## Independent Python prerequisite probe

This is a reproducible installation experiment for Node-based clients. It is
**not a production WorkBuddy launcher** and is not referenced by the marketplace
connector configuration. It neither downloads an embedding model nor creates
a profile, collection or ledger.

With Node.js 20 or newer:

```sh
node --test tests/test_managed_bootstrap.mjs
node integrations/managed/bootstrap.mjs --probe
```

The explicit `--probe` downloads a fixed official uv wheel and checks its
exact byte length and SHA-256. It extracts only the exact regular executable
into a fresh private directory, then asks uv to prepare Python 3.11.15. It does not execute a
remote installer script, invoke an archive utility or require a system Python,
uv/uvx installation, administrator rights or service credentials. uv's managed
Python mechanism uses its pinned python-build-standalone metadata.

The child processes receive a deliberately restricted environment with an empty
PATH, private uv/Python cache/install directories and managed-only Python
selection. The probe checks that the executed Python belongs to that fresh
directory. This remains a command-line prerequisite test on an existing OS,
not a clean WorkBuddy GUI marketplace installation.

Only a fully verified bootstrap executable can run. ZIP paths are never used as
filesystem destinations. Symlink, encrypted and unsafe path entries are refused.
Temporary probe files are retained for explicit inspection/removal and are
separate from all memory data. Service credentials are not passed to uv/Python.
The probe needs access to PyPI and Python distribution download endpoints.

CI exercises Linux x64, Windows x64 and macOS Apple Silicon. A macOS Intel
artifact is included for best-effort experiments only. Intel is not a formal
support or release gate. Other architectures have no support claim here.

Passing this probe establishes only the runtime prerequisite. Python package
installation, explicit embedding-provider selection, backend initialization,
MCP startup within client time limits, restart/upgrade and WorkBuddy GUI
acceptance are separate requirements. In particular, first-time runtime/model
downloads must not block a 30-second MCP handshake. See the
[managed installation design](../../docs/workbuddy-one-click-architecture.md).
