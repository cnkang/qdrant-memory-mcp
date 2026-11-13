# WorkBuddy MCP + Skill connector

For explicitly configured shared access, give WorkBuddy only its own Owner token. Keep Qdrant write keys and Owner state out of connector packages. See [deployment security](../../docs/shared-deployment-security.md). The managed connector remains private by default. It does not enable destination protection.

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
      "args": ["-y", "@cnkang/qdrant-memory-launcher@0.1.0-rc.8", "mcp", "workbuddy", "--auto-setup"],
      "runtime": {"type": "node", "version": "20"},
      "npmRegistries": ["https://registry.npmjs.org"],
      "timeout": 60000
    }
  }
}
```

1. The user installs the connector in WorkBuddy.
2. WorkBuddy prepares managed Node.js 20 and its isolated npm environment.
3. `npx` fetches the exact pinned launcher version. The pin is exact, never
   `latest`. New builds allow only the canonical npm registry. No mirror
   fallback is configured.
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

Older managed CPU profiles use the FastEmbed 0.9.0 pipeline. Launcher rc.8 uses
0.9.1 and must not silently relabel that data or cache. Keep the previous
launcher for the old profile. Export from that profile, then preview re-embedding
into a new profile and collection before importing. Preserve the old store for
rollback and switch WorkBuddy only after verifying the new profile. The managed
launcher always starts WorkBuddy with `profiles/workbuddy/local`; importing into
another profile alone does not change the profile WorkBuddy uses. The pinned
[Runtime 0.6.0 standalone guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/dee6777432f17523db75f6be32cf3ef15e48235c/docs/standalone.md)
documents the migration grammar. Use the procedure below:

The managed launcher does not add `qdrant-memory` to the shell `PATH`. The
managed root is `QDRANT_MEMORY_MANAGED_ROOT` when set, or `qdrant-memory-managed`
under the platform data directory: `~/Library/Application Support` on macOS,
`%LOCALAPPDATA%` on Windows, or `$XDG_DATA_HOME` / `~/.local/share` on Linux.
Each executable is under
`programs/<runtime-revision>/<12-character-dependency-lock-prefix>/<platform>-<architecture>/env/`.
Use the old launcher's pinned Runtime revision for the old profile and the
current revision for the new profile. The executable is `bin/qdrant-memory` on
macOS/Linux and `Scripts/qdrant-memory.exe` on Windows.

Runtime confines explicit `--output` and `--source-json` files to the current
working directory. Run the migration from a private directory so both files
stay inside that boundary. Disconnect WorkBuddy before starting and leave it
disconnected until the profile switch is complete. Wait for its connector
process to exit so no process has the embedded store open. A new Runtime profile
defaults to Ollama, so initialize the staging profile with the managed
FastEmbed provider before importing. On macOS/Linux:

```sh
set -eu
umask 077
ROOT='/absolute/path/to/qdrant-memory-managed'
STAMP="$(date +%Y%m%d%H%M%S)"
OLD_PROFILE="$ROOT/profiles/workbuddy/local"
NEW_PROFILE="$ROOT/profiles/workbuddy/migration-$STAMP"
BACKUP_PROFILE="$ROOT/profiles/workbuddy/local-backup-$STAMP"
MODEL_CACHE="$ROOT/models/workbuddy-migration-$STAMP"
MIGRATION_DIR="$HOME/qdrant-memory-migration-$STAMP"
OLD_RUNTIME="$ROOT/programs/<old-revision>/<dependency-lock-prefix>/<platform>-<architecture>/env/bin/qdrant-memory"
NEW_RUNTIME="$ROOT/programs/<current-revision>/<dependency-lock-prefix>/<platform>-<architecture>/env/bin/qdrant-memory"
NEW_PYTHON="${NEW_RUNTIME%/qdrant-memory}/python"
test -d "$OLD_PROFILE"
test ! -e "$NEW_PROFILE"
test ! -e "$BACKUP_PROFILE"
test ! -e "$MODEL_CACHE"
test -x "$OLD_RUNTIME"
test -x "$NEW_RUNTIME"
test -x "$NEW_PYTHON"
mkdir -m 700 "$MIGRATION_DIR"
cd "$MIGRATION_DIR"
"$NEW_RUNTIME" setup --profile "$NEW_PROFILE" --embedding-provider fastembed \
  --model-cache-dir "$MODEL_CACHE" --user-id my-user --agent-id my-agent
"$OLD_RUNTIME" --home "$OLD_PROFILE" export \
  --user my-user --agent my-agent --output memories.json
EXPORT_COUNT=$("$NEW_PYTHON" -c '
import json
from pathlib import Path

payload = json.loads(Path("memories.json").read_text(encoding="utf-8"))
count = payload.get("count")
records = payload.get("memories")
if type(count) is not int or not isinstance(records, list) or count != len(records):
    raise SystemExit("Export count does not match exported memories.")
print(count)
')
printf 'Exported %s memories for user my-user and agent my-agent.\n' "$EXPORT_COUNT"
if [ "$EXPORT_COUNT" -eq 0 ]; then
  printf 'Export contains zero memories. Type yes only if this scope is expected to be empty: '
  read -r CONFIRM_EMPTY_EXPORT
  if [ "$CONFIRM_EMPTY_EXPORT" != yes ]; then
    printf 'Stopped before importing or switching WorkBuddy profiles.\n' >&2
    exit 1
  fi
fi
"$NEW_RUNTIME" --home "$NEW_PROFILE" migrate mem0 \
  --source-json memories.json --dry-run
"$NEW_RUNTIME" --home "$NEW_PROFILE" migrate mem0 \
  --source-json memories.json --verify
test -d "$NEW_PROFILE"
mv "$OLD_PROFILE" "$BACKUP_PROFILE"
if ! mv "$NEW_PROFILE" "$OLD_PROFILE"; then
  mv "$BACKUP_PROFILE" "$OLD_PROFILE"
  exit 1
fi
test -d "$OLD_PROFILE"
test -d "$BACKUP_PROFILE"
printf 'Profile switched. Keep this rollback stamp: %s\n' "$STAMP"
```

On Windows, use a private PowerShell working directory and the managed
executables under `env\Scripts\qdrant-memory.exe`:

```powershell
$ErrorActionPreference = 'Stop'
$Root = '<absolute-path-to-qdrant-memory-managed>'
$Stamp = Get-Date -Format 'yyyyMMddHHmmss'
$OldProfile = Join-Path $Root 'profiles\workbuddy\local'
$NewProfile = Join-Path $Root "profiles\workbuddy\migration-$Stamp"
$BackupProfile = Join-Path $Root "profiles\workbuddy\local-backup-$Stamp"
$ModelCache = Join-Path $Root "models\workbuddy-migration-$Stamp"
$MigrationDir = Join-Path $HOME "qdrant-memory-migration-$Stamp"
$OldRuntime = Join-Path $Root 'programs\<old-revision>\<dependency-lock-prefix>\<platform>-<architecture>\env\Scripts\qdrant-memory.exe'
$NewRuntime = Join-Path $Root 'programs\<current-revision>\<dependency-lock-prefix>\<platform>-<architecture>\env\Scripts\qdrant-memory.exe'
$NewPython = Join-Path (Split-Path -Parent $NewRuntime) 'python.exe'
if (-not (Test-Path -LiteralPath $OldProfile -PathType Container)) { throw 'Old WorkBuddy profile does not exist.' }
if ((Test-Path -LiteralPath $NewProfile) -or (Test-Path -LiteralPath $BackupProfile)) { throw 'Migration profile path already exists.' }
if (Test-Path -LiteralPath $ModelCache) { throw 'Migration model cache path already exists.' }
if (-not (Test-Path -LiteralPath $OldRuntime -PathType Leaf)) { throw 'Old Runtime executable does not exist.' }
if (-not (Test-Path -LiteralPath $NewRuntime -PathType Leaf)) { throw 'Current Runtime executable does not exist.' }
if (-not (Test-Path -LiteralPath $NewPython -PathType Leaf)) { throw 'Current Runtime Python executable does not exist.' }
New-Item -ItemType Directory -Path $MigrationDir | Out-Null
Set-Location $MigrationDir
& $NewRuntime setup --profile $NewProfile --embedding-provider fastembed --model-cache-dir $ModelCache --user-id my-user --agent-id my-agent
if ($LASTEXITCODE -ne 0) { throw "FastEmbed profile setup failed with exit code $LASTEXITCODE." }
$ExportFile = Join-Path $MigrationDir 'memories.json'
& $OldRuntime --home $OldProfile export --user my-user --agent my-agent --output $ExportFile
if ($LASTEXITCODE -ne 0) { throw "Runtime export failed with exit code $LASTEXITCODE." }
$ExportDocument = Get-Content -LiteralPath $ExportFile -Raw | ConvertFrom-Json
if (
  $null -eq $ExportDocument.PSObject.Properties['count'] -or
  $null -eq $ExportDocument.PSObject.Properties['memories'] -or
  ($ExportDocument.count -isnot [int] -and $ExportDocument.count -isnot [long]) -or
  $ExportDocument.memories -isnot [array] -or
  $ExportDocument.count -ne $ExportDocument.memories.Count
) { throw 'Export count does not match exported memories.' }
$ExportCount = [long]$ExportDocument.count
Write-Host "Exported $ExportCount memories for user my-user and agent my-agent."
if ($ExportCount -eq 0) {
  $ConfirmEmptyExport = Read-Host 'Export contains zero memories. Type yes only if this scope is expected to be empty'
  if ($ConfirmEmptyExport -cne 'yes') { throw 'Stopped before importing or switching WorkBuddy profiles.' }
}
& $NewRuntime --home $NewProfile migrate mem0 --source-json memories.json --dry-run
if ($LASTEXITCODE -ne 0) { throw "Migration dry run failed with exit code $LASTEXITCODE." }
& $NewRuntime --home $NewProfile migrate mem0 --source-json memories.json --verify
if ($LASTEXITCODE -ne 0) { throw "Verified migration failed with exit code $LASTEXITCODE." }
if (-not (Test-Path -LiteralPath $NewProfile -PathType Container)) { throw 'Imported profile was not created.' }
Move-Item -LiteralPath $OldProfile -Destination $BackupProfile
try {
  Move-Item -LiteralPath $NewProfile -Destination $OldProfile
} catch {
  if (-not (Test-Path -LiteralPath $OldProfile) -and (Test-Path -LiteralPath $BackupProfile)) {
    Move-Item -LiteralPath $BackupProfile -Destination $OldProfile
  }
  throw
}
if (-not (Test-Path -LiteralPath $OldProfile -PathType Container)) { throw 'Switched WorkBuddy profile does not exist.' }
if (-not (Test-Path -LiteralPath $BackupProfile -PathType Container)) { throw 'Original WorkBuddy profile backup does not exist.' }
Write-Output "Profile switched. Keep this rollback stamp: $Stamp"
```

Replace `my-user` and `my-agent` with the scope values used by the old profile,
replace each path placeholder with the installed Runtime location, and review
the dry-run output. `MODEL_CACHE` is a unique FastEmbed cache directory under
the managed root's `models/` directory. The migration and backup profiles are
siblings under the managed root so the profile moves stay on the same volume.
Keep the original profile backup until WorkBuddy reconnects and the migrated
memories are verified.

To roll back on macOS/Linux, disconnect WorkBuddy, reuse `ROOT` and `STAMP`
from the migration shell, and run:

```sh
set -eu
OLD_PROFILE="$ROOT/profiles/workbuddy/local"
BACKUP_PROFILE="$ROOT/profiles/workbuddy/local-backup-$STAMP"
FAILED_PROFILE="$ROOT/profiles/workbuddy/migration-failed-$STAMP"
test -d "$OLD_PROFILE"
test -d "$BACKUP_PROFILE"
test ! -e "$FAILED_PROFILE"
mv "$OLD_PROFILE" "$FAILED_PROFILE"
if ! mv "$BACKUP_PROFILE" "$OLD_PROFILE"; then
  mv "$FAILED_PROFILE" "$OLD_PROFILE"
  exit 1
fi
```

On Windows, disconnect WorkBuddy, reuse `$Root` and `$Stamp`, then run:

```powershell
$ErrorActionPreference = 'Stop'
$OldProfile = Join-Path $Root 'profiles\workbuddy\local'
$BackupProfile = Join-Path $Root "profiles\workbuddy\local-backup-$Stamp"
$FailedProfile = Join-Path $Root "profiles\workbuddy\migration-failed-$Stamp"
if (-not (Test-Path -LiteralPath $OldProfile -PathType Container)) { throw 'Current profile does not exist.' }
if (-not (Test-Path -LiteralPath $BackupProfile -PathType Container)) { throw 'Profile backup does not exist.' }
if (Test-Path -LiteralPath $FailedProfile) { throw 'Rollback destination already exists.' }
Move-Item -LiteralPath $OldProfile -Destination $FailedProfile
try {
  Move-Item -LiteralPath $BackupProfile -Destination $OldProfile
} catch {
  if (-not (Test-Path -LiteralPath $OldProfile) -and (Test-Path -LiteralPath $FailedProfile)) {
    Move-Item -LiteralPath $FailedProfile -Destination $OldProfile
  }
  throw
}
```

Connector 0.2.5 records MCP distribution 0.3.1, Runtime 0.6.0, launcher
0.1.0-rc.8 and Skill 0.4.0 in its release provenance. The managed WorkBuddy
route runs launcher 0.1.0-rc.8 to install Runtime 0.6.0 and ships Skill 0.4.0;
it does not install the Python MCP distribution or instantiate Hermes' native
MemoryProvider. The separate Python/uvx alternative below installs MCP
distribution 0.3.1. Verify the exact launcher version on npm and the connector
assets on the corresponding GitHub Release before installing. Previous
connector 0.2.4 archives retain their original per-release provenance and immutable bytes.
The MCP 0.3.2 release candidate targets Runtime 0.6.1 and pins
`qdrant-memory-mcp==0.3.2`. The candidate uvx configuration is only usable
after PyPI publishes MCP 0.3.2; the released
connector instructions below continue to use public MCP 0.3.1.
`provenance.json` inside each ZIP records its versions, launcher
integrity and Skill source commit. Its `runtime_version` identifies the Runtime
installed by the included managed npm launcher (0.6.0 for launcher 0.1.0-rc.8).
It is intentionally independent of the source-only uvx candidate, which targets
Runtime 0.6.1 and is not included in the connector ZIP. The builder rejects
drift from checked-in pins:

- The launcher pin lives in `launcher-source.json` at the repository root and
  records its Runtime version; it must be public on the npm registry with matching integrity before release
  assets are prepared. `mcp.json` lists only the canonical registry
  (`https://registry.npmjs.org`). Package validation rejects additional
  registry entries.
- The Skill pin lives in `integrations/workbuddy/skill-source.json` and must
  match a clean canonical checkout at the exact commit.
- For a future MCP release, update the checked-in uvx alternative's version
  alongside normal package and Registry metadata.

## Alternative: custom MCP with Python/uvx

`mcp.uvx.json` documents the advanced custom-MCP route for users who run
their own Python backend instead of the managed launcher:

The source candidate is `qdrant-memory-mcp==0.3.3` with Runtime 0.6.2. Until
that candidate is published, use the public MCP 0.3.2 pin below.

```sh
uvx --from qdrant-memory-mcp==0.3.2 qdrant-memory-mcp mcp
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
[canonical setup reference](https://github.com/cnkang/skills/blob/5bac228e8594a6cf8ff642c22f0f0e100ebca3a6/qdrant-memory/references/runtime.md)
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
git -C .workbuddy-skill checkout --detach cc592289f126c786fd6c11038fcaa966c6de2b40
python3 -m venv .workbuddy-env
.workbuddy-env/bin/python -m pip install 'PyYAML==6.0.3'
.workbuddy-env/bin/python integrations/workbuddy/build.py --check
.workbuddy-env/bin/python integrations/workbuddy/build.py
unzip -l dist/workbuddy/*-preview.zip
cd dist/workbuddy && shasum -a 256 -c *.sha256
```

Windows uses `.workbuddy-env/Scripts/python.exe`. Python 3.11+ is required.
`--skill-root /path/to/fresh/checkout` selects an existing pinned checkout.
The builder needs no Qdrant, profile or credentials. It emits only the ZIP and the checksum under `dist/workbuddy`. It rejects symlinks and
unsafe resources. It uses sorted STORE ZIP members with fixed dates and modes. It
refuses output bytes that differ from existing bytes. `--check` builds twice in disposable directories and
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
- `tests/public-launcher-acceptance.mjs` runs the exact connector and DSH
  commands through `npx` with the pinned public package. The check covers the
  60-second cold handshake budget, a clean unprepared probe, background
  preparation, refused-but-not-queued writes, CRUD and fresh-process
  persistence. It runs on Linux, macOS and Windows.
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
| First handshake within the connector timeout | PASS (`0.1.0-rc.1`): worst measured cold npx 15.5 seconds (Windows CI). Historical budget 30 seconds; current managed connector budget 60 seconds |
| Search/save/update/delete with synthetic records | PASS (`0.1.0-rc.1`): protocol level through the public npx command, three platforms. Marketplace GUI NOT VERIFIED |
| Restart MCP child. Retrieve persisted synthetic records | PASS (`0.1.0-rc.1`): fresh-process persistence, three platforms. Full application restart NOT VERIFIED |
| Missing embedding and invalid API key fail safely | SDK tested. GUI NOT VERIFIED |
| Same-profile Hermes WriterLease refusal | SDK tested. GUI NOT VERIFIED |

The managed connector was also exercised end to end on macOS. The test used the exact
public npx command with an isolated managed root. It covered the cold handshake,
background preparation, refusal semantics, CRUD, fresh-process persistence and aborted-
preparation resume. These acceptance runs measured the published
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


## Private installation and registry policy

New connector builds use only https://registry.npmjs.org. Mirror fallback is not
part of the reviewed connector configuration. Runtime npx integrity still comes
from that registry. Release-time pin verification is not a per-launch digest
check. Use a host-managed, preverified launcher when that stronger boundary is
required. Existing published assets remain immutable.

On POSIX, preparation now rejects existing managed paths owned by another user
or writable by a group/other users, including unsafe ancestors. Root-owned
non-writable system ancestors and sticky temporary ancestors may be traversed.
The selected managed directory itself must belong to the invoking user. No
existing directory permissions are silently changed. Select a private root or
have its owner repair the permissions before retrying. On Windows, provision a
private inherited ACL. POSIX mode checks do not establish that ACL.
