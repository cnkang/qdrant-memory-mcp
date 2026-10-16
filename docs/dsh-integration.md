# Qdrant Memory for DeepSeek Harness

DSH can search, save, update and delete durable memories through its official
MCP client. Memory survives a new session and server restart. This is explicit
memory: the connection does not automatically save every conversation.

[中文](dsh-integration.zh-CN.md) · [Validation and limitations](dsh-validation.md)

## Use the published Python server

This path requires Python 3.11+, uv/uvx, and a working embedding service, such
as Ollama. Follow the [quickstart](quickstart.md), using a new dedicated profile
at `~/.qdrant-memory-dsh` instead of `~/.qdrant-memory`. Put your chosen scope and
embedding settings in that profile's `qdrant-memory.json`, then initialize it:

```sh
uvx --from qdrant-memory-mcp==0.1.4 qdrant-memory-mcp --home "$HOME/.qdrant-memory-dsh" init
uvx --from qdrant-memory-mcp==0.1.4 qdrant-memory-mcp --home "$HOME/.qdrant-memory-dsh" doctor
dsh web --patch /absolute/path/to/qdrant-memory-mcp/integrations/dsh/qdrant-memory.cordis.yml
```

On Windows use the corresponding absolute profile path. Set
`QDRANT_MEMORY_DSH_PROFILE` before starting DSH to select another private profile.
Do not select an active Hermes/WorkBuddy profile. Prepare dependencies and warm
the Python environment before enabling the overlay. DSH does not install or
initialize third-party servers.

The overlay adds one uniquely identified plugin for this launch. It does not
overwrite any `cordis.patch.yml` or modify the default Profile. To retain it,
keep passing `--patch`, or carefully merge its single `insert` entry into the
chosen profile's patch file. Do not enable the Python and managed overlays
together. Other profiles remain unchanged.

Alternatively, install the [configuration-only Bundle](../integrations/dsh/README.md)
into one chosen profile using DSH's official plugin installation command. Its
`dsh.bundle.patch` declares the same single MCP row. Backend preparation remains
a separate explicit step. Do not install both routes in the same profile.

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

## Optional managed CPU candidate

This source candidate downloads private Python dependencies and a verified CPU
embedding model. It needs Node.js 20+ and network access. No Python/uvx or Ollama
installation is required. It is not yet an npm or marketplace release. Prepare
it explicitly before connecting DSH:

```sh
node /absolute/path/to/integrations/managed/launcher.mjs prepare dsh
export QDRANT_MEMORY_LAUNCHER=/absolute/path/to/integrations/managed/launcher.mjs
dsh web --patch /absolute/path/to/integrations/dsh/managed.cordis.yml
```

Wait for `{"ready":true,"host":"dsh"}`. Downloads can take several minutes.
The DSH MCP probe only starts the prepared server. It does not run setup or
download models. The managed profile is separate from the Python overlay's
profile. See [managed launcher](../integrations/managed/README.md) before use.

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

To disconnect, remove this launch's overlay or disable its plugin in the selected
profile. DSH closes the MCP process. Data stays on disk. Verify persistence by
saving a synthetic fact and recalling it in a new session without the old
transcript. Then update or delete the returned ID and fully restart DSH.
Real model/GUI acceptance is separate from the automated official-client suite.

The adapter follows the official
[MCP client contract](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md),
[memory guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/mcp-memory.md)
and [Skill filesystem provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md).
