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

This adapter targets `@deepseek-ai/dsh@0.2.2-rc.1`. Runtime 0.6.2 is now
published on PyPI, but the native adapter package remains private and real-model
or GUI acceptance is incomplete. Use the Bundle or Python/uvx overlay below for
a published installation path. See [native design and support status](dsh-native/design.md).
See the [English setup guide](../integrations/dsh/native/README.md),
[中文设置说明](../integrations/dsh/native/README.zh-CN.md), and
[validation evidence](dsh-native/validation.md) for configuration, rollback,
and the current test boundaries.

## Alternative: Python/uvx overlay

The 0.3.3 MCP release candidate pins the published Runtime 0.6.2 and will use
`qdrant-memory-mcp==0.3.3`. It is not a published PyPI package yet, so the
working commands below intentionally remain pinned to public MCP 0.3.2. Switch
this overlay only after the 0.3.3 PyPI page and artifacts are available.

Run the pinned 0.3.2 commands below. `qdrant-memory-mcp` 0.3.2 is published
on PyPI; no source checkout is required for this overlay lane.

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
Before launch it also inspects `dsh web --dump-config` for the current profile.
An existing `qdrant-memory` server or any server-name conflict with the overlay
blocks launch; remove the existing memory connection before using this overlay.
The dump is parsed as YAML nodes without evaluating tags, and its temporary
file is removed after the check. A failed or invalid dump also blocks launch.

```sh
PROFILE="${QDRANT_MEMORY_DSH_PROFILE:-$HOME/.qdrant-memory-dsh}"
export QDRANT_MEMORY_DSH_PROFILE="$PROFILE"
uvx --from qdrant-memory-mcp==0.3.2 qdrant-memory-mcp --home "$PROFILE" init &&
uvx --from qdrant-memory-mcp==0.3.2 qdrant-memory-mcp --home "$PROFILE" doctor &&
(
  mkdir -p "$PROFILE"
  PATCH="$PROFILE/qdrant-memory.cordis.yml"
  if [ ! -e "$PATCH" ]; then
    TMP="$(mktemp "${PATCH}.XXXXXX")"
    # Bash can exit before the failure branch runs, for example on Ctrl-C, so
    # keep the partial file out of the profile directory in every exit path.
    trap 'rm -f "$TMP"' EXIT INT
    if curl -fsSL -o "$TMP" \
      https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.2/integrations/dsh/qdrant-memory.cordis.yml; then
      mv "$TMP" "$PATCH"
      trap - EXIT INT
    else
      rm -f "$TMP"
      echo "Patch download failed; DSH was not launched." >&2
      exit 1  # This setup block is a subshell, safe when sourced too.
    fi
  fi
  # Parse YAML nodes only: !!js expressions are never evaluated.
  COMPOSED="$(mktemp)"
  if dsh web --dump-config > "$COMPOSED"; then
    if uv run --no-project --with PyYAML==6.0.3 python -I - "$PATCH" qdrant-memory-mcp==0.3.2 "$PROFILE" "$COMPOSED" <<'PY'
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


def profile_servers(node, ancestors=()):
    """Inspect composed YAML nodes without evaluating tags or following cycles."""
    assert id(node) not in ancestors, 'Cyclic profile YAML'
    if isinstance(node, MappingNode):
        item = mapping(node)
        assert not (item.get('id') and item['id'].value == 'cnkang-qdrant-memory-mcp'), 'Memory plugin already installed'
        name = item.get('name')
        group = item.get('group')
        is_group = group is not None and group.value == 'true'
        # Plugin groups store their child entries under config. Inspect those
        # entries even when the group itself has no profile id.
        if not item.get('id') and not is_group and not (
            name and name.value == '@deepseek-ai/dsh-mcp-client'
        ):
            return
        if name and name.value == '@deepseek-ai/dsh-mcp-client':
            assert name.tag == 'tag:yaml.org,2002:str'
            server = mapping(item['config'])['serverName']
            assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
            yield server.value
        children = [item['config']] if is_group and isinstance(item.get('config'), SequenceNode) else [
            value for _, value in node.value
        ]
    elif isinstance(node, SequenceNode):
        children = node.value
    else:
        return
    for child in children:
        yield from profile_servers(child, (*ancestors, id(node)))


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
    with open(sys.argv[4], encoding='utf-8-sig') as source:
        composed = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(composed, SequenceNode), 'Invalid composed profile'
    existing = list(profile_servers(composed))
    assert 'qdrant-memory' not in existing, 'Memory server already installed'
    assert len(servers + existing) == len(set(servers + existing)), 'Conflicting MCP serverName'
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
    sys.exit('Invalid patch: require one unambiguous memory server, qdrant-memory-mcp==0.3.2 and the prepared profile; DSH was not launched.')
PY
    then
      rm -f "$COMPOSED"
      dsh web --patch "$PATCH"
    else
      rm -f "$COMPOSED"
      false
    fi
  else
    rm -f "$COMPOSED"
    echo "Profile config dump failed; DSH was not launched." >&2
    false
  fi
)
```

On Windows PowerShell 5.1, use the equivalent commands:

```powershell
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  throw "uvx is required; DSH was not launched."
}
$MemoryProfile = if ($env:QDRANT_MEMORY_DSH_PROFILE) { $env:QDRANT_MEMORY_DSH_PROFILE } else { Join-Path $HOME ".qdrant-memory-dsh" }
$env:QDRANT_MEMORY_DSH_PROFILE = $MemoryProfile
uvx --from qdrant-memory-mcp==0.3.2 qdrant-memory-mcp --home $MemoryProfile init
if ($LASTEXITCODE -ne 0) { throw "Runtime init failed; DSH was not launched." }
uvx --from qdrant-memory-mcp==0.3.2 qdrant-memory-mcp --home $MemoryProfile doctor
if ($LASTEXITCODE -ne 0) { throw "Runtime doctor failed; DSH was not launched." }
$PatchDir = $MemoryProfile
$Patch = Join-Path $PatchDir "qdrant-memory.cordis.yml"
New-Item -ItemType Directory -Force -Path $PatchDir | Out-Null
if (-not (Test-Path $Patch)) {
  $Draft = "$Patch.download"
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.2/integrations/dsh/qdrant-memory.cordis.yml" -OutFile $Draft -ErrorAction Stop
    Move-Item -Force $Draft $Patch
  } catch {
    # Write-Error keeps running under the default error preference; a thrown
    # string stops before the config dump can report a misleading failure.
    throw "Patch download failed; DSH was not launched."
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


def profile_servers(node, ancestors=()):
    """Inspect composed YAML nodes without evaluating tags or following cycles."""
    assert id(node) not in ancestors, 'Cyclic profile YAML'
    if isinstance(node, MappingNode):
        item = mapping(node)
        assert not (item.get('id') and item['id'].value == 'cnkang-qdrant-memory-mcp'), 'Memory plugin already installed'
        name = item.get('name')
        group = item.get('group')
        is_group = group is not None and group.value == 'true'
        # Plugin groups store their child entries under config. Inspect those
        # entries even when the group itself has no profile id.
        if not item.get('id') and not is_group and not (
            name and name.value == '@deepseek-ai/dsh-mcp-client'
        ):
            return
        if name and name.value == '@deepseek-ai/dsh-mcp-client':
            assert name.tag == 'tag:yaml.org,2002:str'
            server = mapping(item['config'])['serverName']
            assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
            yield server.value
        children = [item['config']] if is_group and isinstance(item.get('config'), SequenceNode) else [
            value for _, value in node.value
        ]
    elif isinstance(node, SequenceNode):
        children = node.value
    else:
        return
    for child in children:
        yield from profile_servers(child, (*ancestors, id(node)))


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
    with open(sys.argv[4], encoding='utf-8-sig') as source:
        composed = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(composed, SequenceNode), 'Invalid composed profile'
    existing = list(profile_servers(composed))
    assert 'qdrant-memory' not in existing, 'Memory server already installed'
    assert len(servers + existing) == len(set(servers + existing)), 'Conflicting MCP serverName'
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
    sys.exit('Invalid patch: require one unambiguous memory server, qdrant-memory-mcp==0.3.2 and the prepared profile; DSH was not launched.')
'@
$Composed = [IO.Path]::GetTempFileName()
try {
  $ConsoleEncoding = [Console]::OutputEncoding
  try {
    # PowerShell decodes native stdout using Console.OutputEncoding.
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $Dump = @(dsh web --dump-config)
  } finally {
    [Console]::OutputEncoding = $ConsoleEncoding
  }
  if ($LASTEXITCODE -ne 0) { throw "Profile config dump failed; DSH was not launched." }
  [IO.File]::WriteAllText($Composed, ($Dump -join "`n"))
  $ValidatePatch | uv run --no-project --with PyYAML==6.0.3 python -I - $Patch qdrant-memory-mcp==0.3.2 $MemoryProfile $Composed
  if ($LASTEXITCODE -ne 0) { throw "Patch/profile validation failed; DSH was not launched." }
} finally {
  Remove-Item -Force $Composed -ErrorAction SilentlyContinue
}
dsh web --patch $Patch
```

The overlay patch is part of the published `v0.3.2` tag, so fetch it directly;
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
