# Qdrant Memory for DeepSeek Harness

Shared deployments require separate Owner client tokens and Owner-only database write credentials. See [deployment security](shared-deployment-security.md). The ordinary managed bundle stays private and does not enroll a shared destination.

DSH can search, save, update and delete durable memories through its official
MCP client. Memory survives a new session and server restart. This is explicit
memory for the published MCP paths: the connection does not automatically save
every conversation.

[中文](dsh-integration.zh-CN.md) · [Validation and limitations](dsh-validation.md)

## Install the Bundle (managed CPU)

The configuration-only Bundle connects the public launcher through the
official `@deepseek-ai/dsh-mcp-client`. It needs Node.js (which DSH already
uses) and no system Python, uvx, Ollama or Qdrant Server. Prepare the shared
backend first:

```sh
npx -y @cnkang/qdrant-memory-launcher@0.1.0-rc.8 prepare dsh
```

Wait for `{"ready":true,"host":"dsh"}`. Preparation downloads the private
Python environment, the pinned Runtime wheel and a verified CPU embedding
model. It can take several minutes and needs network access. Then install the
Bundle into one profile:

```sh
dsh plugin --profile <name> add @cnkang/qdrant-memory-dsh-bundle
```

If your registry has not served the package yet, download
`cnkang-qdrant-memory-dsh-bundle-0.1.6.tgz` from the repository release and
install the file path instead. Verify the layer without booting:

```sh
dsh --profile <name> --dump-config
```

DSH starts a temporary probe before the persistent connection. The probe never
runs installation or model downloads. Preparation is always the explicit step
above. Until the backend is ready, tools report that no operation occurred.
Writes are never queued. The DSH profile
(`<managed-root>/profiles/dsh/local`) is separate from WorkBuddy and Hermes
profiles. See the [Bundle README](../integrations/dsh/bundle/README.md) for
update, uninstall and recovery details.

## Native lifecycle adapter (unreleased preview)

The repository also contains an optional [native Cordis adapter](../integrations/dsh/native/README.md).
It uses DSH's model and session lifecycle for opt-in recall, injection, and
completed-turn candidate extraction, then sends the candidates to the existing
Python Owner. All three switches default to `false`. Recall requires both
`auto_recall.enabled` and `memory_injection.enabled`.

This adapter targets `@deepseek-ai/dsh@0.2.2-rc.1`. The compatible Runtime
change is merged at 0.6.1 but not yet published on PyPI, so the native path is
not a supported install with current published packages. Use the Bundle or
Python/uvx overlay below until Runtime 0.6.1 is released. The
native package is not published, and it has no real-model or GUI acceptance
claim. See [native design and support status](dsh-native/design.md).
See the [English setup guide](../integrations/dsh/native/README.md),
[中文设置说明](../integrations/dsh/native/README.zh-CN.md), and
[validation evidence](dsh-native/validation.md) for configuration, rollback,
and the current test boundaries.

## Alternative: Python/uvx overlay

Run the pinned 0.3.1 commands below. `qdrant-memory-mcp` 0.3.1 is published
on PyPI; no source checkout is required for this lane.

This path requires Python 3.11+, uv/uvx, and a working embedding service, such
as Ollama. Follow the [quickstart](quickstart.md), using a new dedicated profile
at `~/.qdrant-memory-dsh` instead of `~/.qdrant-memory`. Put your chosen scope and
embedding settings in that profile's `qdrant-memory.json`, then initialize it:

```sh
PROFILE="${QDRANT_MEMORY_DSH_PROFILE:-$HOME/.qdrant-memory-dsh}"
export QDRANT_MEMORY_DSH_PROFILE="$PROFILE"
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home "$PROFILE" init &&
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home "$PROFILE" doctor &&
{
  mkdir -p "$PROFILE"
  PATCH="$PROFILE/qdrant-memory.cordis.yml"
  if [ ! -e "$PATCH" ]; then
    TMP="$(mktemp "${PATCH}.XXXXXX")"
    if curl -fsSL -o "$TMP" \
      https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.1/integrations/dsh/qdrant-memory.cordis.yml; then
      mv "$TMP" "$PATCH"
    else
      rm -f "$TMP"
      echo "Patch download failed; DSH was not launched." >&2
    fi
  fi
  if [ -e "$PATCH" ] && grep -q 'qdrant-memory-mcp==0.3.0' "$PATCH"; then
    echo "The existing patch still pins qdrant-memory-mcp==0.3.0; update it to 0.3.1 before launching DSH." >&2
  elif [ -e "$PATCH" ]; then
    dsh web --patch "$PATCH"
  fi
}
```

On Windows PowerShell 5.1, use the equivalent commands:

```powershell
$Profile = if ($env:QDRANT_MEMORY_DSH_PROFILE) { $env:QDRANT_MEMORY_DSH_PROFILE } else { Join-Path $HOME ".qdrant-memory-dsh" }
$env:QDRANT_MEMORY_DSH_PROFILE = $Profile
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home $Profile init
if ($LASTEXITCODE -ne 0) { throw "Runtime init failed; DSH was not launched." }
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home $Profile doctor
if ($LASTEXITCODE -ne 0) { throw "Runtime doctor failed; DSH was not launched." }
$PatchDir = $Profile
$Patch = Join-Path $PatchDir "qdrant-memory.cordis.yml"
New-Item -ItemType Directory -Force -Path $PatchDir | Out-Null
if (-not (Test-Path $Patch)) {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.1/integrations/dsh/qdrant-memory.cordis.yml" -OutFile $Patch -ErrorAction Stop
  } catch {
    Write-Error "Patch download failed; DSH was not launched."
  }
}
if (-not (Test-Path $Patch)) {
  Write-Error "Patch is unavailable; DSH was not launched."
} elseif (Select-String -Path $Patch -Pattern 'qdrant-memory-mcp==0\.3\.0' -Quiet) {
  Write-Error "The existing patch still pins qdrant-memory-mcp==0.3.0; update it to 0.3.1 before launching DSH."
} else {
  dsh web --patch $Patch
}
```

The overlay patch is part of the published `v0.3.1` tag, so fetch it directly;
no source checkout is required. Keep the downloaded file outside the package
environment and pass its local path to `--patch` on every DSH launch.

On Windows use the corresponding absolute profile path. Set
`QDRANT_MEMORY_DSH_PROFILE` before starting DSH to select another private profile.
Do not select an active Hermes/WorkBuddy profile. Prepare dependencies and warm
the Python environment before enabling the overlay. DSH does not install or
initialize third-party servers.

The overlay adds one uniquely identified plugin for this launch. It does not
overwrite any `cordis.patch.yml` or modify the default Profile. To retain it,
keep passing `--patch`, or carefully merge its single `insert` entry into the
chosen profile's patch file. Do not enable the Python overlay and the Bundle
together in one profile. Other profiles remain unchanged.

DSH prefixes tools as `mcp__qdrant-memory__qdrant_memory_search`, `...add`,
`...update` and `...delete`. If you change `serverName`, use the names actually
discovered. Raw MCP schemas and scope restrictions remain unchanged. Approve
tools through DSH's normal permission controls.

## Load the shared Skill

Install the canonical `qdrant-memory` directory, with its references, under
your project's `.agents/skills/` or a configured DSH Skill root. The source is
[`cnkang/skills`](https://github.com/cnkang/skills/tree/main/qdrant-memory).
For example, symlink a reviewed checkout's `qdrant-memory` directory to
`.agents/skills/qdrant-memory` on systems supporting symlinks, or use DSH's
`customSkillDirs` setting to scan that checkout. DSH's filesystem provider
discovers `qdrant-memory/SKILL.md`. No separately maintained DSH Skill is needed.
Select one canonical version if other roots already contain the same Skill.

## Credentials and troubleshooting

DSH removes inherited environment variables whose names contain KEY, PASSWORD,
SECRET or TOKEN, and `DSH_*`. The Python overlay explicitly forwards
`QDRANT_API_KEY` and `EMBEDDING_API_KEY` from the environment. Use your trusted
shell/secret manager to set those values. Never paste them into YAML, command
arguments, Skill text or logs. Add other credential variable names explicitly
if your profile references them. Empty values are suitable only for backends
that do not require those credentials. The managed CPU preset needs no keys.

If tools report preparation pending/failed, no operation succeeded. Fix setup
before retrying. Reconnect is not a substitute for provisioning. If an operation
was interrupted after dispatch, check the exact operation and its ID before any
repeat. Do not repeat an uncertain write unless a repeat is safe for that
operation. A busy-profile error means another process owns storage. Close that
connection normally.
Never remove a data lock, reset storage or change a fingerprint to force startup.

To disconnect, remove the Bundle or the overlay of this launch. Then stop or restart the
profile. A running profile keeps its loaded Bundle set. Only the stop or the restart
closes the active MCP process and releases the storage writer lease. Data stays on disk. Verify persistence by saving a synthetic fact and
recalling it in a new session without the old transcript. Then update or delete
the returned ID and fully restart DSH.
Real model/GUI acceptance is separate from the automated official-client suite.

The adapter follows the official
[MCP client contract](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md),
[memory guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/mcp-memory.md)
and [Skill filesystem provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md).
