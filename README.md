# Qdrant Memory MCP

For shared production deployments, read the [deployment security guide](docs/shared-deployment-security.md). Owner-only database write credentials are required independently of MCP grants. Destination protection and shared doctor are unpublished Runtime additions. Published pins and installation commands remain unchanged.

## One Memory, Multiple Agents — opt-in shared owner

The distribution adds an opt-in single-owner service and stdio bridge. Install Runtime 0.4.0 to use them. See [shared integration guide](integrations/shared/README.md). Private defaults are unchanged. Native Provider automatic shared extraction is deferred.

<!-- mcp-name: io.github.cnkang/qdrant-memory -->

A [WorkBuddy connector](integrations/workbuddy/README.md) and a
[DeepSeek Harness bundle](integrations/dsh/bundle/README.md) reuse this stdio
MCP, the managed launcher and the canonical Skill.

[简体中文](README.zh-CN.md)

Persistent, scoped memory for AI agents through four explicit **stdio MCP** tools.
This repository distributes the existing [Python Runtime](https://github.com/cnkang/hermes-plugin-qdrant-memory).
Its metadata-only wheel contains no Python business implementation. The console
script points directly to `qdrant_memory.standalone:main` and depends on
`hermes-plugin-qdrant-memory[mcp]==0.4.0`.

See [0.1.4 release notes](docs/releases/0.1.4.md) for WorkBuddy assets, SDK compatibility and upgrade guidance.

Before using an exact-version installation command, confirm that version on
the [PyPI release page](https://pypi.org/project/qdrant-memory-mcp/0.2.2/).

**Versions:** MCP distribution 0.2.2 pins Runtime 0.4.0, which supports MCP
Python SDK 1.x and 2.x (`mcp>=1.30,<3`). The four scoped tools and stdio
launch arguments are the same for both SDK majors. It retains the fix for explicit
writes of distinct, highly similar texts without an LLM. The commands below use
these exact versions. Release
artifacts are available through the [distribution PyPI page](https://pypi.org/project/qdrant-memory-mcp/)
and [Runtime PyPI page](https://pypi.org/project/hermes-plugin-qdrant-memory/).
See [release checklist](docs/publishing.md) for the publishing sequence.

Runtime, [optional Agent Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory)
and MCP distribution versions are independent. The Skill is usage guidance,
not a runtime dependency. Hermes retains its native MemoryProvider, automatic
extraction and prefetch. Ordinary MCP performs only explicitly requested memory
operations. It does not automatically extract every conversation turn.

## Install and initialize

For the shortest currently supported local setup, follow the
[Ollama quickstart](docs/quickstart.md) ([中文](docs/quickstart.zh-CN.md)).
It covers an existing model, installing a missing model, a separate WorkBuddy
profile, connection settings and a first save/search check. No Qdrant server,
Docker, cloud account or embedding API key is needed for that local path.
Python/uv and one-time profile configuration are still required for this
direct route. The managed WorkBuddy connector and DSH bundle prepare those
dependencies from Node.js instead.

Requires Python 3.11+ and either [uv](https://docs.astral.sh/uv/) or a Python
virtual environment. You must configure storage and an embedding service.
For the example below, run Ollama and install `qwen3-embedding:4b` yourself.

Create an operator-owned profile directory and save `qdrant-memory.json` inside:

```json
{
  "schema_version": 1,
  "scope": {"user_id": "my-user", "agent_id": "my-agent"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "mode": "plugin", "provider": "ollama", "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434", "dimensions": 2560, "distance": "Cosine"
  }
}
```

Initialize, then launch (replace `/path/to/profile` with your absolute path):

```bash
uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp --home /path/to/profile init
uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp --home /path/to/profile mcp
```

The command without `--home` uses `~/.qdrant-memory`, independent of Hermes.
Configure and initialize that directory before letting a Registry client launch
`uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp mcp`.
The executable name matches the package name.
The Registry's positional `mcp` selects protocol mode. Its optional named
`--home` precedes `mcp` when a client supplies a custom profile.

Alternatively:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install qdrant-memory-mcp==0.2.2
.venv/bin/qdrant-memory-mcp --home /path/to/profile init
.venv/bin/qdrant-memory-mcp --home /path/to/profile mcp
```

On Windows use `.venv\Scripts\python.exe` and
`.venv\Scripts\qdrant-memory-mcp.exe`.

Qdrant embedded, self-hosted server and Cloud, plus Ollama and OpenAI-compatible
embeddings, are configured in the Runtime's [configuration reference](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/configuration.md).
Keep credentials in operator environment variables (`QDRANT_API_KEY`,
`EMBEDDING_API_KEY`, or configured names). Never commit their values.
Initialization against an existing collection requires explicit operator choice.
Do not use a production destination for a first test.

## Connect a client

Codex `config.toml` example:

```toml
[mcp_servers.qdrant_memory]
command = "uvx"
args = ["--from", "qdrant-memory-mcp==0.2.2", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"]
```

OpenCode `opencode.json` example:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "qdrant_memory": {
      "type": "local",
      "command": ["uvx", "--from", "qdrant-memory-mcp==0.2.2", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"],
      "enabled": true
    }
  }
}
```

Pi needs a separately installed MCP client/extension. In that extension, use
`command: uvx` and the same argument list. No built-in Pi MCP support or universal
extension config format is claimed. These are configuration examples. This
distribution's acceptance tests use the official Python MCP SDK, not live agent
applications. See the Runtime's [client evidence and limits](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/mcp.md).

## Tools and boundaries

| Tool | Input | Result |
|---|---|---|
| `qdrant_memory_search` | `query`, optional `category` | Scoped memories with IDs, scores and provenance |
| `qdrant_memory_add` | `text` | Durable memory ID |
| `qdrant_memory_update` | exact `id`, replacement `text` | Scoped replacement |
| `qdrant_memory_delete` | exact `id` | Scoped deletion |

Scope is fixed by the operator's profile (`user_id`, `agent_id`). Model inputs
and MCP client identity cannot override it. Knowing an ID does not grant access.
Migration, export, reset and bulk deletion remain trusted operator CLI commands.
See [standalone maintenance](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/standalone.md).
No resources or prompts are advertised. This is a local subprocess, with no
public HTTP/SSE listener or remote authentication service. Stdout is reserved
for protocol messages, with sanitized diagnostics on stderr.

Data flows from client → Runtime → embedding provider → Qdrant and the local
SQLite ledger. With local Ollama and embedded Qdrant, memory processing stays
local. Cloud embedding receives memory/query text, and cloud Qdrant receives
vectors and stored payloads. The client/model may also receive recalled text.
The operator must authorize retention and access and protect the profile files.

One writer lease coordinates a profile/destination. Do not overlap MCP, CLI
or Hermes processes writing to it. Separate profiles or machines do not provide
a distributed lock. This package does not support uncoordinated multiprocess
writes, auto-extraction, an HTTP transport, or implicit credential discovery
from Hermes. It preserves the Runtime's ledger, IDs and recovery semantics.

## Verification and development

CI builds wheel/sdist, checks metadata and ownership marker. It runs installed
protocol tests with temporary profiles, embedded Qdrant and a deterministic
loopback embedding fixture on Linux/macOS/Windows, Python 3.11 and 3.14.
No test connects to personal Qdrant, Hermes profiles or memory data. These tests
cover initialize, discovery, four tools, persistence, recovery, scope isolation,
error redaction and protocol stdout. Provider/cloud compatibility evidence
belongs to the [Runtime](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/validation.md).

CI prefers the immutable Runtime PyPI release. Before a Runtime release reaches
PyPI, CI builds a wheel from the immutable revision recorded in `runtime-source.json`. This is only a preparation fixture:
published dependency metadata always uses the exact PyPI version. Release
workflow acceptance requires installation from PyPI and never uses that fallback.

See [CI and dependency maintenance](docs/ci.md), [publishing](docs/publishing.md), [architecture](docs/architecture.md), and
the optional [Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory).

## WorkBuddy and DeepSeek Harness

Use the [WorkBuddy connector](integrations/workbuddy/README.md) or the
[DSH installation guide](docs/dsh-integration.md) for explicit durable memory.
Both reuse the Python Runtime, the four MCP tools and the canonical Skill. The published [managed launcher](integrations/managed/README.md) prepares private Python
and CPU-model dependencies with Node.js. Thus, the managed routes do not require a
system Python, uvx or Ollama installation. The DSH Bundle is
distributed as `@cnkang/qdrant-memory-dsh-bundle`. Existing Hermes profiles
and defaults are unchanged. See [architecture and version matrix](docs/cross-harness-architecture.md)
and [validation limits](docs/dsh-validation.md).
