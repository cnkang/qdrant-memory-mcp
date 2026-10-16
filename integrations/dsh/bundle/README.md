# Qdrant Memory Bundle for DeepSeek Harness

A configuration-only DSH Bundle. It connects one prepared Qdrant Memory
profile through the official `@deepseek-ai/dsh-mcp-client`. It contains no
memory engine, no embeddings and no Python code. The shared Qdrant Memory
launcher and Runtime own storage, scope, ledger and recovery.

The Bundle declares one patch layer: a single `qdrant-memory` MCP server entry.
DSH exposes its four tools as `mcp__qdrant-memory__qdrant_memory_search`,
`..._add`, `..._update` and `..._delete`. Explicit operations only. The
connection never captures conversation turns automatically.

## Requirements

- DeepSeek Harness with the official MCP client (`@deepseek-ai/dsh-mcp-client`).
  The tested client line is `>=0.2.0-rc.2 <0.3.0`.
- Node.js 20 or newer for `npx`. DSH already runs on Node.js.
- Network access for the first launcher download and for backend preparation
  (private Python, Runtime wheel and CPU model artifacts, about 250 MB).
- Free disk space for the managed root: programs, models and host profiles.

No system Python, uv/uvx, Ollama or Qdrant Server is required. The managed
root defaults to `qdrant-memory-managed` under the platform data directory
(`~/Library/Application Support` on macOS, `%LOCALAPPDATA%` on Windows,
`$XDG_DATA_HOME` or `~/.local/share` on Linux). Set an absolute
`QDRANT_MEMORY_MANAGED_ROOT` before starting DSH to use another location.

## Prepare the backend first

The DSH MCP probe is temporary and must never run installation or downloads.
Prepare the shared backend explicitly, once:

```sh
npx -y @cnkang/qdrant-memory-launcher@0.1.0-rc.2 prepare dsh
```

Preparation downloads the private Python environment, the Runtime wheel and a
verified CPU embedding model. It may take several minutes. Wait for
`{"ready":true,"host":"dsh"}`. The DSH profile is separate from WorkBuddy and
Hermes profiles. Preparation never deletes existing memory data.

## Install into one profile

```sh
dsh plugin --profile <name> add @cnkang/qdrant-memory-dsh-bundle
```

If the npm registry has not served this package yet, install the release
tarball instead. Download `@cnkang-qdrant-memory-dsh-bundle-0.1.0.tgz` from
the repository release and run:

```sh
dsh plugin --profile <name> add ./cnkang-qdrant-memory-dsh-bundle-0.1.0.tgz
```

Verify the layer without booting:

```sh
dsh --profile <name> --dump-config
```

The output contains one `# == @cnkang/qdrant-memory-dsh-bundle` section with
the `cnkang-qdrant-memory-mcp` row. Then boot the profile. The four
`mcp__qdrant-memory__*` tools appear after discovery. Wait for preparation to
finish before you ask the agent to save a fact. Until the backend is ready,
tool calls report that no operation succeeded. Writes are never queued.

The first connection authorizes downloads and creation of the private DSH
profile. Do not enable this Bundle and a Qdrant Memory overlay in the same
profile. One profile has one owner for embedded storage.

## Update

```sh
dsh plugin --profile <name> update @cnkang/qdrant-memory-dsh-bundle
```

Disconnect the profile before an upgrade. Program versions install alongside
earlier versions. Profile, ledger and collection files remain in place. After
an upgrade, run `prepare dsh` again to refresh shared programs and the model
cache. A profile never migrates or resets itself. Incompatible data fails
closed.

## Uninstall

```sh
dsh plugin --profile <name> remove @cnkang/qdrant-memory-dsh-bundle
```

Removing the Bundle removes the MCP entry. It does not delete the managed
root, the prepared profile or any memory. Closing the profile releases the
storage writer lease. Never delete a `.provision.lock` file or Runtime data
locks while a process may still own them.

## Recovery

- A connection indicator or four discovered tools do not mean the backend is
  ready. If a call reports preparation pending or failed, no operation
  succeeded. Fix preparation before retrying.
- After an interrupted write, search for the affected memory and check its
  exact ID before repeating the operation. Never repeat an uncertain write
  unless a repeat is safe for that operation.
- A busy-profile error means another process owns the profile. Close that
  connection normally. Never remove locks to force a second writer.
- An interrupted installation can leave a provisioning lock. Confirm that
  the installer and its child processes have stopped, then inspect only that
  program's `.provision.lock`. Never reset a profile to bypass ownership.

## License

MIT. See `LICENSE`. Third-party attributes are listed in the shared launcher
package.
