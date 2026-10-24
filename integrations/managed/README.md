# Managed Qdrant Memory launcher

The launcher installs a private Python environment, Runtime 0.5.0 and a
verified multilingual CPU embedding model. WorkBuddy and DeepSeek Harness use
separate embedded memory profiles. Existing Hermes installations keep their
configuration and data.

This is a release candidate. Marketplace installation and desktop acceptance
are tracked separately for each operating system.

## Install and prepare

For a client that already supplies Node.js 20 or newer:

```sh
npm install --global @cnkang/qdrant-memory-launcher@0.1.0-rc.6
qdrant-memory-launcher prepare dsh
qdrant-memory-launcher mcp dsh
```

Preparation needs network access and may take several minutes. It downloads
private Python dependencies and about 252 MB of model artifacts. No system
Python, uv/uvx, Ollama or Qdrant Server is required. The local preset needs no
API keys. DSH must finish preparation before you enable the MCP connection.
Its temporary MCP probe never runs installation.

WorkBuddy's managed Connector declares Node.js 20 and requires WorkBuddy
5.0.0 or newer. It runs `mcp workbuddy --auto-setup`. Installing that connection
authorizes downloads and creation of its private profile.

## First connection and recovery

The four tools appear while preparation runs. A connection indicator means the
MCP transport is available. It does not mean the memory backend is ready.
During preparation, tool calls report that no operation occurred. Wait before
asking the agent to save a fact. Writes are never queued.

After an ordinary network interruption, check the connection and available disk
space, then disconnect and reconnect WorkBuddy to retry. DSH users should run
`qdrant-memory-launcher prepare dsh` again before reconnecting. A failed setup
does not reset memory data. Preparation does not retry downloads indefinitely.

If a save, update or delete was interrupted after dispatch, search for the
affected memory and check its ID before repeating it. Reconnection never
automatically repeats a write.

A busy-profile error means another process owns that profile. Close that
connection normally. Never remove data locks to force a second writer.

## Storage and upgrades

The default root is `qdrant-memory-managed` under:

| System | Data directory |
| --- | --- |
| macOS | `~/Library/Application Support` |
| Windows | `%LOCALAPPDATA%` |
| Linux | `$XDG_DATA_HOME` or `~/.local/share` |

Program environments live under `programs/`, models under `models/`, and
host data under `profiles/workbuddy/local/` or `profiles/dsh/local/`.
The optional `QDRANT_MEMORY_MANAGED_ROOT` must be an absolute path.
Program versions and dependency locks select separate installation directories.
Existing profiles retain their model-cache settings during an upgrade.

Disconnect the client before upgrading or using maintenance commands.
Uninstalling the npm package removes the launcher. It does not remove profiles
or models. Back up the profile before a rollback and retain the same embedding
pipeline. Do not copy a running embedded store or automatically migrate it.

After an unexpected OS shutdown or force-killed installation, a provisioning
lock may require operator assistance. Confirm that the installer and its child
processes have stopped before inspecting only that program's
`.provision.lock`. Do not remove profile files or Runtime data locks.

## Package integrity

The launcher contains no third-party JavaScript dependencies or downloaded
models. It verifies bootstrap and public Runtime 0.5.0 wheel bytes before execution.
All Python dependencies are pinned with hashes and installed as wheels. No
dependency source code is compiled. Runtime verifies model revisions and artifacts.

Pillow stays at 13.0.0. FastEmbed 0.9.0 still declares an upper bound below 13,
so preparation uses the Runtime's existing metadata-only compatibility builder.
The builder source is pinned by immutable commit, size and SHA-256 in
`runtime.json` and verified before the private Python executes it. Its output
`0.9.0+qm.pillow13` wheel is also checked against a fixed size and hash before
installation. Inference files stay unchanged. `uv pip check` remains required.
The verified wheel is reused when an interrupted installation resumes.

Remove this temporary path after an official FastEmbed release supports Pillow
13 and passes the same CPU model and dependency checks. Do not lower Pillow to
resolve its upstream constraint. Existing profiles and model caches are retained.

`runtime.json`, `requirements.lock` and `bootstrap.mjs` record the exact
versions and integrity checks. See [third-party notices](THIRD_PARTY_NOTICES.md).
Installer subprocesses receive a restricted environment without service keys.
MCP stdout carries only protocol messages.
