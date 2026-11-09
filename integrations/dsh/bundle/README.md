# Qdrant Memory Bundle for DeepSeek Harness

A Host Bundle under the existing npm name. Candidate `0.2.0-rc.1` retains
Legacy MCP by default and adds explicitly selected Owner modes. It contains
no memory engine, embeddings or Python code. The Python Runtime owns writes,
scope, ledger and recovery. The private `native/` directory is canonical source
included by the reviewed packer; it is not a second npm publication.

The Bundle declares one patch layer: a single `qdrant-memory` MCP server entry.
In Legacy and Unified Owner mode, DSH exposes four tools as `mcp__qdrant-memory__qdrant_memory_search`,
`..._add`, `..._update` and `..._delete`. Explicit operations only. The
default configuration never captures conversation turns automatically.

## Candidate storage modes

| `mode` | Explicit tools | Automatic memory | Storage |
| --- | --- | --- | --- |
| `legacy` (default) | Four existing MCP tools | Rejected if enabled | Existing prepared launcher profile |
| `native-owner` | None from this Bundle | Opt-in | Authenticated HTTPS Owner |
| `unified-owner` | Four official HTTP MCP tools | Opt-in | The same HTTPS endpoint and token for both paths |

Select a mode in this Bundle's configuration before enabling
`auto_capture.enabled`, `auto_recall.enabled` and `memory_injection.enabled`.
Recall needs both the recall and injection switches. Legacy needs no Owner
token. Owner modes require an absolute `QDRANT_MEMORY_RUNTIME_PYTHON`,
`QDRANT_MEMORY_DSH_OWNER_URL` with exact HTTPS `/mcp`, and a provisioned
`QDRANT_MEMORY_DSH_OWNER_TOKEN`. For a private CA, configure
`QDRANT_MEMORY_RUNTIME_CA_FILE` for Python and `NODE_EXTRA_CA_CERTS` at Host
startup for the official Node MCP client. Never put tokens in profile YAML.

One trusted identity owns one DSH profile. Do not share an Owner-enabled Host
among independently authorized users. Grants come from the Owner policy,
never model content or a supplied user/agent/scope field. Do not install this
Bundle alongside the old overlay or the private Native bundle.
Owner modes refuse activation while an existing `qdrant-memory` MCP route
still exposes tools, before opening another connection.

Changing mode does not migrate any data. Legacy and remote Owner data remain
separate until an operator explicitly previews, backs up, verifies and approves
a migration. No migration is performed by this package. Disable and stop the
old connection before changing storage targets. Incompatible embedding spaces
must be resolved through the Runtime's explicit migration workflow.

Capture writes a content-free activation watermark in the durable DSH Session.
First enable excludes earlier turns; disable/re-enable establishes a new
boundary. HMR retains the enabled boundary for receipt recovery. Backfill is
not provided. Recovery drains batches of eight with a sixteen-turn live queue;
it currently reads the full individual Session log once per recovery pass.

Prepare the candidate tarball with `python scripts/pack_dsh_bundle.py
--output-dir dist/dsh-bundle` from the repository root. Direct `npm pack` of
this source directory omits the canonical Native module and is not a release
artifact. Publication requires approved Runtime 0.6.1 public-wheel, protected
Cloud and Desktop acceptance. When approved, publish this candidate under
`next`, keeping `latest=0.1.6`; this task does not publish either package.

## Requirements

- DeepSeek Harness `0.2.2-rc.1`, enforced by `engines.dsh`. Earlier Hosts
  remain on Bundle 0.1.6 until explicitly upgraded.
- Node.js 24.9.0 or newer. This is a compatibility boundary of candidate 0.2.
- `pnpm` on `PATH` for `dsh plugin --profile <name> add`: the official DSH
  plugin manager forwards installation to pnpm.
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
npx -y @cnkang/qdrant-memory-launcher@0.1.0-rc.8 prepare dsh
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
tarball instead. Download `cnkang-qdrant-memory-dsh-bundle-0.1.6.tgz` from
the repository release and run:

```sh
dsh plugin --profile <name> add ./cnkang-qdrant-memory-dsh-bundle-0.1.6.tgz
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

Disconnect the profile before an upgrade. FastEmbed 0.9.0-to-0.9.1 upgrades require an authorized export and
re-embedding into a new profile/collection; keep the previous launcher and data
until verification. See [pipeline upgrade guidance](https://github.com/cnkang/qdrant-memory-mcp/blob/main/integrations/managed/README.md#package-integrity).
For upgrades within the same pipeline, program versions install alongside
earlier versions. Profile, ledger and collection files remain in place. After
an upgrade, run `prepare dsh` again to refresh shared programs and the model
cache. A profile never migrates or resets itself. Incompatible data fails
closed.

## Uninstall

```sh
dsh plugin --profile <name> remove @cnkang/qdrant-memory-dsh-bundle
```

Removal edits the profile manifest. A running profile keeps its loaded
Bundle set: stop or restart the profile to close the active MCP connection
and release the storage writer lease. Removal does not delete the managed
root, the prepared profile or any memory. Never delete a `.provision.lock`
file or Runtime data locks while a process may still own them.

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
