# Connect an agent

For shared mode, use [shared-memory setup](shared-memory.md) and [security boundaries](shared-security.md). Give each agent only its fixed-grant Owner token. Never add database write keys or mount Owner state into an agent.

Install/configure the [runtime](runtime.md) and verify `init` and `doctor` for an
authorized private profile. Use absolute executable/profile paths. Merge only
the selected MCP entry into existing settings. Skill loading does not authorize
setup changes.

## Codex CLI

```bash
codex mcp add qdrant-memory -- /private/path/qdrant-env/bin/qdrant-memory \
  --home /private/path/profile mcp
codex mcp list
```

Check `codex mcp add --help` for the installed CLI's options.

## Claude Code

```bash
claude mcp add --transport stdio qdrant-memory -- \
  /private/path/qdrant-env/bin/qdrant-memory --home /private/path/profile mcp
```

Choose local/project/user configuration scope deliberately. See the
[official guide](https://code.claude.com/docs/en/mcp).

## OpenCode

Use the installed CLI to register the local server:

```bash
opencode mcp add qdrant-memory -- /private/path/qdrant-env/bin/qdrant-memory \
  --home /private/path/profile mcp
opencode mcp list
```

For manual config, V1 puts entries directly under `mcp` with `enabled`. V2 uses
`mcp.servers` and optional `disabled`. Consult the matching
[V1 guide](https://opencode.ai/docs/mcp-servers/) or
[V2 guide](https://dev.opencode.ai/v2/docs/mcp-servers/) before editing.

## Pi

```bash
pi mcp add qdrant-memory -- /private/path/qdrant-env/bin/qdrant-memory \
  --home /private/path/profile mcp
pi mcp list
```

Older Pi versions may need upgrading. See [Pi MCP documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md).
Load the skill with `/skill:qdrant-memory` after installation/discovery.

## Other agents and Hermes

Compatible stdio MCP clients can discover four `qdrant_memory_*` tools. Hosts
may prefix their names. Agents with command execution can use the JSON CLI through
[usage](usage.md). Interface compatibility is not a claim that every host/model
has been tested.

Hermes users can keep native tools and `hermes qdrant-memory` without switching
profiles. Its CLI provides maintenance/migration. Standalone adds scoped CRUD.
Avoid concurrent embedded writers against the same storage.

Use one memory interface for each Hermes profile: the native plugin or the
qdrant-memory MCP server, not both. Before you register this MCP server,
check `hermes plugins list` for qdrant-memory. If the plugin is installed, ask the user to enable it when needed (`hermes plugins
enable qdrant-memory`). Then run `hermes memory setup` and select qdrant-memory as the
memory provider. After that, do not add this server for Hermes. Inform the user that
Hermes needs no further setup. Other agents can still use this server or the
CLI. If the plugin cannot be used for that profile, register this server for
that profile instead. If the plugin is not installed, recommend it for Hermes
first: the Plugin Catalog provides `hermes plugins install qdrant-memory` and
the same setup step. Two interfaces show the same tools twice and contend for
one writer lease. The skill instructions are compatible and do not add tools.
