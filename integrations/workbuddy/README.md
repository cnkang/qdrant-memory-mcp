# WorkBuddy MCP + Skill connector

This adapter packages the shared Python memory runtime and the canonical Skill
as a WorkBuddy connector. It implements no memory engine, changes no Runtime
code and adds no Python modules to the metadata-only MCP wheel. Explicit
search/add/update/delete remain the four MCP tools. Hermes automatic
extraction and prefetch remain Hermes features.

## How installation works

The shipped connector starts the published managed launcher through
WorkBuddy's managed Node.js runtime. `mcp.json` declares:

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@cnkang/qdrant-memory-launcher@0.1.0-rc.2", "mcp", "workbuddy", "--auto-setup"],
      "runtime": {"type": "node", "version": "20"},
      "npmRegistries": ["https://registry.npmjs.org", "https://registry.npmmirror.com"],
      "timeout": 30000
    }
  }
}
```

1. The user installs the connector in WorkBuddy.
2. WorkBuddy prepares managed Node.js 20 and its isolated npm environment.
3. `npx` fetches the exact pinned launcher version. The pin is exact, never
   `latest`. The npm registry list is an ordered fallback. The canonical
   registry is always first.
4. The launcher completes the MCP handshake promptly and exposes the four
   tools. In the background it prepares a private Python environment, the
   pinned Runtime wheel and a verified CPU embedding model.
5. Until preparation finishes, every tool call reports that no operation
   occurred. No write is queued and no write is replayed later.
6. Search, save, update and delete then work against a WorkBuddy-specific
   managed profile. Restarts reuse the same profile and data.

No system Python, uv/uvx, Ollama, or Qdrant Server installation is required.
The launcher verifies bootstrap and Runtime wheel bytes and installs only
hash-locked wheels. The local preset needs no API keys.

## Requirements

- WorkBuddy 5.0.0 or newer. The managed Node runtime and npm registry fields
  require that client line.
- Network access for the first launcher download and for backend preparation.
- About 300 MB of disk space for the private programs and the CPU model.
- First preparation can take several minutes. Later connections start warm.

## First connection and readiness

- The connector declaration and a connected status only mean the MCP
  transport is available. They do not mean the memory backend is ready. Wait
  before asking the agent to save a fact.
- During preparation, tool calls return an explicit "no operation performed"
  error. Retry after preparation. Never queue a write. Do not repeat an
  uncertain write unless a repeat is safe for that operation.
- If an operation was interrupted after dispatch, search for the affected
  memory and check its exact ID before repeating it.
- A busy-profile error means another process owns that profile. Close that
  connection normally. Never remove data locks to bypass ownership.

## Storage, updates and recovery

The default managed root is `qdrant-memory-managed` under the platform data
directory:

| System | Data directory |
| --- | --- |
| macOS | `~/Library/Application Support` |
| Windows | `%LOCALAPPDATA%` |
| Linux | `$XDG_DATA_HOME` or `~/.local/share` |

Program environments live under `programs/`, models under `models/`, and the
host profile under `profiles/workbuddy/local/`. Set an absolute
`QDRANT_MEMORY_MANAGED_ROOT` for a custom location. Program versions and
dependency locks select separate installation directories. Existing profiles
keep their own model-cache settings during an upgrade.

Disconnect the connector before upgrading. Uninstalling the connector removes
the launcher processes it started. It does not remove profiles, models or
memory data. Back up the profile before a rollback and retain the same
embedding pipeline. Do not copy a running embedded store or migrate it
automatically.

After an ordinary network interruption, check the connection and free disk
space, then disconnect and reconnect to retry preparation. A failed
preparation never resets memory data. The launcher does not retry downloads
indefinitely. After an unexpected OS shutdown or a force-killed installation,
a provisioning lock may require operator inspection. Confirm that the
installer and its child processes stopped before inspecting only that
program's `.provision.lock`. Never remove profile files or Runtime data locks.

## Update and versioning

Connector 0.2.0, MCP 0.1.4, Runtime 0.3.0, launcher 0.1.0-rc.2 and Skill 0.2.6
are independent versions. `provenance.json` inside the ZIP records all
versions, the launcher integrity and the Skill source commit. The builder
rejects drift from the checked-in pins:

- The launcher pin lives in `launcher-source.json` at the repository root and
  must be public on the npm registry with matching integrity before release
  assets are prepared. Additional registries listed in `mcp.json` are
  best-effort cross-checked against the canonical registry. A conflict fails
  the gate.
- The Skill pin lives in `integrations/workbuddy/skill-source.json` and must
  match a clean canonical checkout at the exact commit.
- For a future MCP release, update the checked-in uvx alternative's version
  alongside normal package and Registry metadata.

## Alternative: custom MCP with Python/uvx

`mcp.uvx.json` documents the advanced custom-MCP route for users who run
their own Python backend instead of the managed launcher:

```sh
uvx --from qdrant-memory-mcp==0.1.4 qdrant-memory-mcp mcp
```

Add `--home <private-profile-path>` before `mcp` to bind an explicit private
profile directory. That route requires Python 3.11+, uv/uvx, a separately prepared profile and an
embedding service such as Ollama. Warm the pinned package before connecting.
Network installation can exceed the 30-second connection timeout. Never use a
personal Hermes profile for WorkBuddy. Never initialize an existing
collection without the owner's authorization.

Keep credentials out of this package, command arguments, examples and logs.
Supply `QDRANT_API_KEY` and `EMBEDDING_API_KEY` through a private process
environment or secret manager. `QDRANT_URL` alone is not profile
initialization. Cloud's database URL is not an MCP endpoint. A future Cloud
connector must verify the whole form-to-profile configuration path before
declaring managed support. Cloud storage remains operator-configured.

## Configure a private profile (alternative route)

For a new authorized local profile, create `qdrant-memory.json` privately:

```json
{
  "scope": {"user_id": "local-user", "agent_id": "workbuddy"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "provider": "ollama", "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434", "dimensions": 2560
  }
}
```

Use the actual installed model and its dimensions. Install and start Ollama
separately. For the uvx route, run the pinned `qdrant-memory-mcp` command with `init`,
then `doctor`, in place of `mcp`, and pass `--home <private-profile-path>`
for the authorized target. Check service readiness before
connecting. For self-hosted or Cloud storage, follow the Runtime's documented
server/cloud profile configuration. See the
[canonical setup reference](https://github.com/cnkang/skills/blob/042c3feadd77ef8099140fd1bfc9d7d03bdfaf78/qdrant-memory/references/runtime.md)
and [Runtime configuration](https://github.com/cnkang/hermes-plugin-qdrant-memory).

Scope is operator-configured. Client names and tool arguments cannot switch
identity. Separate users need separate profiles and process credentials.
Embedded storage and WriterLease require exclusive profile access. Close
Hermes's writer before opening the same profile through WorkBuddy. Independent
profiles do not provide a distributed lease for the same remote collection.

## The managed profile

The managed preset writes `profiles/workbuddy/local/qdrant-memory.json` with
the `workbuddy` agent identity and a FastEmbed CPU embedding provider. The
model revision and all wheel hashes are pinned in the launcher package. The
profile is created privately (owner-only permissions). It never imports
Hermes or DSH configuration and never writes into their data directories.

## Connection and troubleshooting

Use WorkBuddy's connector import or marketplace path when available. Verify
all four tools with synthetic data before real use. Skill installation does
not initialize storage or authorize memory writes.

- If the first connection reports preparation failures, check network and
  disk space, then disconnect and reconnect.
- Embedding failures return sanitized error types. Run `doctor` privately to
  diagnose a custom profile.
- Invalid credentials fail safely. Never debug by publishing profile files.
- If `WriterBusyError` occurs, stop the competing authorized writer and
  retry. Never bypass the lease or modify the ledger directly.

## Build a preview

From this repository, use a fresh canonical source checkout and a private
build environment (the Skill builder needs PyYAML):

```sh
git clone --no-checkout https://github.com/cnkang/skills.git .workbuddy-skill
git -C .workbuddy-skill checkout --detach 042c3feadd77ef8099140fd1bfc9d7d03bdfaf78
python3 -m venv .workbuddy-env
.workbuddy-env/bin/python -m pip install 'PyYAML==6.0.3'
.workbuddy-env/bin/python integrations/workbuddy/build.py --check
.workbuddy-env/bin/python integrations/workbuddy/build.py
unzip -l dist/workbuddy/*-preview.zip
cd dist/workbuddy && shasum -a 256 -c *.sha256
```

Windows uses `.workbuddy-env/Scripts/python.exe`. Python 3.11+ is required.
`--skill-root /path/to/fresh/checkout` selects an existing pinned checkout.
The builder needs no Qdrant, profile or credentials. It emits only ZIP and
checksum under `dist/workbuddy`, rejects symlinks and unsafe resources, uses
sorted STORE ZIP members with fixed dates and modes, and refuses differing
existing output bytes. `--check` builds twice in disposable directories and
compares exact bytes.

```text
qdrant-memory-workbuddy/
  connector-meta.json
  mcp.json
  icon.svg
  provenance.json
  skills/qdrant-memory/
    SKILL.md
    LICENSE
    references/...
    scripts/...
```

No generated Skill, ZIP, database or profile is committed. The preview
workflow uses read-only permissions and retains the
`workbuddy-connector-preview` artifact for 14 days.

## Verification and acceptance

Automated acceptance in this repository:

- Deterministic connector build, manifest/provenance checks and exact-pin
  guards run in `workbuddy-preview.yml` on every change.
- `public_install.py` verifies that the pinned launcher version is public on
  the npm registry with matching integrity. The release workflow refuses to
  prepare assets while this check fails.
- `tests/public-launcher-acceptance.mjs` runs the exact connector command and
  the exact DSH command through `npx` with the pinned public package:
  cold handshake budget, a clean unprepared probe, background preparation,
  refused-but-not-queued writes, CRUD and fresh-process persistence. It runs
  on Linux, macOS and Windows.
- The uvx alternative is exercised with the actual public PyPI pin once a
  release is published.

The table below records client-level acceptance. Record the actual client
version, OS, isolation path and observations before marking any GUI row
passed. Do not use existing personal memory for acceptance.

| WorkBuddy client acceptance | Status |
|---|---|
| Import ZIP. Bilingual metadata/icon/Skill resources | NOT VERIFIED |
| Managed Node preparation and first connection, no developer tools | NOT VERIFIED |
| Connect via custom managed entry. Discover exactly four tools | PASS: macOS, WorkBuddy 5.8.2 (custom entry, earlier round) |
| Cold preparation of Python, dependencies and CPU model | PASS: public npx command (`0.1.0-rc.1`), local macOS run and three-platform CI |
| First handshake within the connector timeout | PASS (`0.1.0-rc.1`): worst measured cold npx 15.5 seconds (Windows CI). Budget 30 seconds |
| Search/save/update/delete with synthetic records | PASS (`0.1.0-rc.1`): protocol level through the public npx command, three platforms. Marketplace GUI NOT VERIFIED |
| Restart MCP child. Retrieve persisted synthetic records | PASS (`0.1.0-rc.1`): fresh-process persistence, three platforms. Full application restart NOT VERIFIED |
| Missing embedding and invalid API key fail safely | SDK tested. GUI NOT VERIFIED |
| Same-profile Hermes WriterLease refusal | SDK tested. GUI NOT VERIFIED |

The managed connector was additionally exercised end to end on macOS through
the exact public npx command with an isolated managed root: cold handshake,
background preparation, refusal semantics, CRUD, fresh-process persistence and
aborted-preparation resume. These acceptance runs measured the published
`0.1.0-rc.1` tarball. The pinned `0.1.0-rc.2` re-ran the same acceptance
after its publication on 2026-10-16 and passed on Linux, macOS and Windows
CI plus a local macOS run. GUI-level marketplace ZIP import, managed-Node
provisioning and a full application restart on a clean machine remain
maintainer gates before marketplace submission.

## Release and recovery

Only an approved MCP version tag matching package metadata and merged main can
trigger release preparation. `workbuddy-release.yml` builds and tests with
`contents: read`. A dependent minimal `contents: write` job validates the
downloaded ZIP, checksum and provenance, then attaches assets to a Draft. It
never executes upstream Skill code, publishes the Draft, touches
PyPI/Registry, or moves tags.

Reruns compare bytes and reuse matching assets. A conflict, or a published
release missing attachments, fails without replacement. Investigate
toolchain/source drift, preserve old assets and tags, and prepare a new
approved release if necessary. Rollback means selecting the previous reviewed
connector, package and profile backup. Never republish an existing PyPI
version or rewrite a release tag.

For DSH use its [own bundle and guide](../../docs/dsh-integration.md).
