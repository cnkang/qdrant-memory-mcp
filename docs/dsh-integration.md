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

Before running initialization, create and configure `qdrant-memory.json` in the
directory selected by `QDRANT_MEMORY_DSH_PROFILE` (scope, embedding model, and
service address). A fresh selected directory does not inherit settings from
`~/.qdrant-memory-dsh`; `init`, `doctor`, and the MCP server all use the selected
directory.
Use an absolute path such as `"$HOME/memory"` for a literal
`QDRANT_MEMORY_DSH_PROFILE` value; `~/memory` is not expanded inside a quoted
variable. The examples expand the fallback with `$HOME` so shell file operations
and the Runtime select the same directory.

Before reusing an existing patch, verify that its `--home` points at the selected
profile; update it before launch if it hardcodes another home.

The launch guard uses uv to fetch pinned PyYAML and inspects YAML nodes without
evaluating `!!js` tags. It accepts the documented `config.args` prefix with
`--from PACKAGE` or `--from=PACKAGE` in an insert-only overlay. Other patch
operations fail before launch because they could override the validated args.
The guard also rejects duplicate MCP server names and a `--home` that differs
from the prepared profile. Keep the published dynamic home expression or use
the prepared profile's literal path.

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
  # Parse YAML nodes only: !!js expressions are never evaluated.
  if uv run --no-project --with PyYAML==6.0.3 python -I - "$PATCH" qdrant-memory-mcp==0.3.1 "$PROFILE" <<'PY'
import sys
import yaml
from pathlib import Path
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


def mapping(node):
    """Read a mapping without constructing or evaluating tagged values."""
    assert isinstance(node, MappingNode)
    result = {}
    for key, value in node.value:
        assert isinstance(key, ScalarNode) and key.tag == 'tag:yaml.org,2002:str'
        assert key.value not in result, 'Duplicate YAML key'
        result[key.value] = value
    return result


try:
    with open(sys.argv[1], encoding='utf-8') as source:
        root = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(root, SequenceNode)
    plugins = []
    servers = []
    for operation in root.value:
        entries = mapping(operation)['insert']
        assert isinstance(entries, SequenceNode)
        for entry in entries.value:
            plugin = mapping(entry)
            name = plugin.get('name')
            if name is not None:
                assert isinstance(name, ScalarNode) and name.tag == 'tag:yaml.org,2002:str'
            if name and name.value == '@deepseek-ai/dsh-mcp-client':
                server = mapping(plugin['config'])['serverName']
                assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
                servers.append(server.value)
            if plugin.get('id') and plugin['id'].value == 'cnkang-qdrant-memory-mcp':
                plugins.append(plugin)
    assert len(plugins) == 1, 'Expected exactly one memory plugin'
    name = plugins[0]['name']
    assert name.tag == 'tag:yaml.org,2002:str' and name.value == '@deepseek-ai/dsh-mcp-client'
    config = mapping(plugins[0]['config'])
    assert len(servers) == len(set(servers)), 'Conflicting MCP serverName'
    command = config['command']
    assert command.tag == 'tag:yaml.org,2002:str' and command.value == 'uvx'
    args = config['args']
    assert isinstance(args, SequenceNode)
    # Tagged values stay as YAML nodes and are never evaluated.
    prefix = []
    for arg in args.value[:3]:
        assert isinstance(arg, ScalarNode) and arg.tag == 'tag:yaml.org,2002:str'
        prefix.append(arg.value)
    package = sys.argv[2]
    assert (prefix == ['--from', package, 'qdrant-memory-mcp']
            or prefix[:2] == ['--from=' + package, 'qdrant-memory-mcp'])
    tail = args.value[3 if prefix[0] == '--from' else 2:]
    assert len(tail) in (2, 3) and tail[-1].value == 'mcp'
    assert tail[-1].tag == 'tag:yaml.org,2002:str'
    if len(tail) == 3:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value == '--home'
        home = tail[1]
    else:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value.startswith('--home=')
        home = ScalarNode('tag:yaml.org,2002:str', tail[0].value[len('--home='):])
    assert isinstance(home, ScalarNode)
    if home.tag == 'tag:yaml.org,2002:js':
        trusted = (
            "process.env.QDRANT_MEMORY_DSH_PROFILE || "
            "require('node:path').join(require('node:os').homedir(), '.qdrant-memory-dsh')"
        )
        assert ' '.join(home.value.split()) == trusted, 'Unverified dynamic home'
    else:
        assert home.tag == 'tag:yaml.org,2002:str'
        assert Path(home.value).expanduser().resolve() == Path(sys.argv[3]).expanduser().resolve(), 'Profile mismatch'
except (AssertionError, KeyError, AttributeError, OSError, yaml.YAMLError):
    sys.exit('Invalid patch: require one unambiguous memory server, qdrant-memory-mcp==0.3.1 and the prepared profile; DSH was not launched.')
PY
  then
    dsh web --patch "$PATCH"
  else
    false
  fi
}
```

On Windows PowerShell 5.1, use the equivalent commands:

```powershell
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  throw "uvx is required; DSH was not launched."
}
$MemoryProfile = if ($env:QDRANT_MEMORY_DSH_PROFILE) { $env:QDRANT_MEMORY_DSH_PROFILE } else { Join-Path $HOME ".qdrant-memory-dsh" }
$env:QDRANT_MEMORY_DSH_PROFILE = $MemoryProfile
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home $MemoryProfile init
if ($LASTEXITCODE -ne 0) { throw "Runtime init failed; DSH was not launched." }
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home $MemoryProfile doctor
if ($LASTEXITCODE -ne 0) { throw "Runtime doctor failed; DSH was not launched." }
$PatchDir = $MemoryProfile
$Patch = Join-Path $PatchDir "qdrant-memory.cordis.yml"
New-Item -ItemType Directory -Force -Path $PatchDir | Out-Null
if (-not (Test-Path $Patch)) {
  $Draft = "$Patch.download"
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.1/integrations/dsh/qdrant-memory.cordis.yml" -OutFile $Draft -ErrorAction Stop
    Move-Item -Force $Draft $Patch
  } catch {
    Write-Error "Patch download failed; DSH was not launched."
  } finally {
    Remove-Item -Force $Draft -ErrorAction SilentlyContinue
  }
}
# Parse YAML nodes only: !!js expressions are never evaluated.
$ValidatePatch = @'
import sys
import yaml
from pathlib import Path
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


def mapping(node):
    """Read a mapping without constructing or evaluating tagged values."""
    assert isinstance(node, MappingNode)
    result = {}
    for key, value in node.value:
        assert isinstance(key, ScalarNode) and key.tag == 'tag:yaml.org,2002:str'
        assert key.value not in result, 'Duplicate YAML key'
        result[key.value] = value
    return result


try:
    with open(sys.argv[1], encoding='utf-8') as source:
        root = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(root, SequenceNode)
    plugins = []
    servers = []
    for operation in root.value:
        entries = mapping(operation)['insert']
        assert isinstance(entries, SequenceNode)
        for entry in entries.value:
            plugin = mapping(entry)
            name = plugin.get('name')
            if name is not None:
                assert isinstance(name, ScalarNode) and name.tag == 'tag:yaml.org,2002:str'
            if name and name.value == '@deepseek-ai/dsh-mcp-client':
                server = mapping(plugin['config'])['serverName']
                assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
                servers.append(server.value)
            if plugin.get('id') and plugin['id'].value == 'cnkang-qdrant-memory-mcp':
                plugins.append(plugin)
    assert len(plugins) == 1, 'Expected exactly one memory plugin'
    name = plugins[0]['name']
    assert name.tag == 'tag:yaml.org,2002:str' and name.value == '@deepseek-ai/dsh-mcp-client'
    config = mapping(plugins[0]['config'])
    assert len(servers) == len(set(servers)), 'Conflicting MCP serverName'
    command = config['command']
    assert command.tag == 'tag:yaml.org,2002:str' and command.value == 'uvx'
    args = config['args']
    assert isinstance(args, SequenceNode)
    # Tagged values stay as YAML nodes and are never evaluated.
    prefix = []
    for arg in args.value[:3]:
        assert isinstance(arg, ScalarNode) and arg.tag == 'tag:yaml.org,2002:str'
        prefix.append(arg.value)
    package = sys.argv[2]
    assert (prefix == ['--from', package, 'qdrant-memory-mcp']
            or prefix[:2] == ['--from=' + package, 'qdrant-memory-mcp'])
    tail = args.value[3 if prefix[0] == '--from' else 2:]
    assert len(tail) in (2, 3) and tail[-1].value == 'mcp'
    assert tail[-1].tag == 'tag:yaml.org,2002:str'
    if len(tail) == 3:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value == '--home'
        home = tail[1]
    else:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value.startswith('--home=')
        home = ScalarNode('tag:yaml.org,2002:str', tail[0].value[len('--home='):])
    assert isinstance(home, ScalarNode)
    if home.tag == 'tag:yaml.org,2002:js':
        trusted = (
            "process.env.QDRANT_MEMORY_DSH_PROFILE || "
            "require('node:path').join(require('node:os').homedir(), '.qdrant-memory-dsh')"
        )
        assert ' '.join(home.value.split()) == trusted, 'Unverified dynamic home'
    else:
        assert home.tag == 'tag:yaml.org,2002:str'
        assert Path(home.value).expanduser().resolve() == Path(sys.argv[3]).expanduser().resolve(), 'Profile mismatch'
except (AssertionError, KeyError, AttributeError, OSError, yaml.YAMLError):
    sys.exit('Invalid patch: require one unambiguous memory server, qdrant-memory-mcp==0.3.1 and the prepared profile; DSH was not launched.')
'@
$ValidatePatch | uv run --no-project --with PyYAML==6.0.3 python -I - $Patch qdrant-memory-mcp==0.3.1 $MemoryProfile
if ($LASTEXITCODE -ne 0) { throw "Patch validation failed; DSH was not launched." }
dsh web --patch $Patch
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
