# Qdrant Memory MCP

**One Memory. Multiple Agents. No Lock-in.**

For Codex and other non-Hermes agents, the primary path is the public stable
stdio MCP distribution. Start with the [quickstart](docs/quickstart.md)
([中文](docs/quickstart.zh-CN.md)): `qdrant-memory-mcp==0.3.5` pins Runtime
0.7.1 and exposes four explicit memory tools. Hermes users should use the
[native Plugin Catalog guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/INSTALL.md).

Durable, portable, and permission-aware memory for AI agents — distributed as
an MCP adapter over the Qdrant Memory Runtime.

For shared production deployments, read the [deployment security guide](docs/shared-deployment-security.md). Owner-only database write credentials are required independently of MCP grants. Configure destination protection and shared doctor before deployment. See the [Owner support record](docs/universal-owner-status.md) for support limits.

## One Memory, Multiple Agents — opt-in shared owner

The distribution adds an opt-in single-owner service and stdio bridge. Install Runtime 0.7.1 to use them. See [shared integration guide](integrations/shared/README.md). Private defaults are unchanged. Native Provider automatic shared extraction is deferred.

<!-- mcp-name: io.github.cnkang/qdrant-memory -->

A [WorkBuddy connector](integrations/workbuddy/README.md) and a
[DeepSeek Harness bundle](integrations/dsh/bundle/README.md) reuse this stdio
MCP, the managed launcher and the canonical Skill.

[简体中文](README.zh-CN.md)

## Published paths and verification

| Path | Published artifact and pin | Current status and acceptance boundary |
|---|---|---|
| [Stable stdio MCP](docs/quickstart.md) | PyPI `qdrant-memory-mcp==0.3.5`, Runtime 0.7.1 | Public stable release; protocol CI uses isolated profiles and a deterministic embedding fixture. This does not establish every live model/provider combination. |
| [Codex plugin](plugins/qdrant-memory/README.md) | Candidate 0.1.4; MCP 0.3.5, Runtime 0.7.1 (`cc5cac025f5d18afb5c698b2b5db444e30fc240e`), Skill 0.4.6 (`9fb5ee0d72a656cedfe1950e08204c437599c4d8`) | Not submitted to the public plugin directory. Official Codex CLI checks are recorded; Desktop GUI and native-memory adoption are separate. |
| [DSH Bundle](docs/dsh-integration.md) | Public npm prerelease `@cnkang/qdrant-memory-dsh-bundle@0.2.0-rc.3`; DSH 0.2.2-rc.1, launcher 0.1.0-rc.12, Runtime 0.7.1 | Installable prerelease. Protected live-model/Cloud and Desktop GUI acceptance remain incomplete. |
| [WorkBuddy connector](integrations/workbuddy/README.md) | GitHub release `workbuddy-v0.2.6`; launcher 0.1.0-rc.10, Runtime 0.6.2, Skill 0.4.4 | Exact-tag packaging and protocol gates passed. Marketplace GUI import, clean-machine provisioning and full application restart remain unverified. |

The host adapters keep independent versions. A candidate or npm-installable RC
does not imply model, Cloud, Desktop or marketplace acceptance. See each linked
host guide and its evidence before choosing an adapter.

Persistent, scoped memory for AI agents through four explicit **stdio MCP** tools.
This repository distributes the existing [Python Runtime](https://github.com/cnkang/hermes-plugin-qdrant-memory).
Its metadata-only wheel contains no Python business implementation. The console
script points directly to `qdrant_memory.standalone:main` and depends on
`hermes-plugin-qdrant-memory[mcp]==0.7.1`.

See [0.3.5 release notes](docs/releases/0.3.5.md) for the Runtime pin and upgrade guidance.

Before using an exact-version installation command, confirm that version on
the [PyPI release page](https://pypi.org/project/qdrant-memory-mcp/0.3.5/).
The [published 0.3.4 guide](https://github.com/cnkang/qdrant-memory-mcp/blob/v0.3.4/README.md) remains available for the previous release.

**Versions:** MCP distribution 0.3.5 pins Runtime 0.7.1, which supports MCP
Python SDK 1.x and 2.x (`mcp>=1.30,<3`). The four scoped tools and stdio
launch arguments are the same for both SDK majors. The commands below use
these exact versions. Release
artifacts are available through the [distribution PyPI page](https://pypi.org/project/qdrant-memory-mcp/)
and [Runtime PyPI page](https://pypi.org/project/hermes-plugin-qdrant-memory/).
See [release checklist](docs/publishing.md) for the publishing sequence.

Runtime, [optional Agent Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory)
and MCP distribution versions are independent. The Skill is usage guidance,
not a runtime dependency. Hermes retains its native MemoryProvider, automatic
extraction and prefetch. Ordinary MCP performs only explicitly requested memory
operations. It does not automatically extract every conversation turn.

## Harness support matrix

Verification levels: configuration example only, protocol-level tested, official
SDK/CLI tested, real host tested, real desktop GUI tested, not verified.

| Host | Native Provider | Explicit MCP tools | Automatic capture | Automatic recall | Shared Owner | Remote access | Verification |
|---|---|---|---|---|---|---|---|
| Hermes | Yes | Yes (via standalone) | Yes | Yes | Opt-in | Yes | Real host tested |
| OpenCode | No | Yes | No | No | Via Owner | Yes | Real host tested (dual-device) |
| Pi | No | Yes (extension) | Opt-in adapter | Opt-in adapter | Via Owner | Yes | Real host tested |
| DeepSeek Harness | No (lifecycle adapter) | Yes (DSH bundle) | Opt-in preview | Opt-in preview | Via Owner | Yes | DSH 0.2.2-rc.1 CI host tested; real model/GUI unverified |
| WorkBuddy | No | Yes (connector) | No | No | Via Owner | Yes | Real desktop GUI tested |
| Codex | No | Yes | No | No | Via Owner | Yes | Official CLI tested |
| VS Code Copilot | No | Yes (four MCP tools) | No | No | Via Owner | Yes | [CI config/protocol PASS](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/44061227907); Copilot CLI 1.0.112 PASS; VS Code 1.146.0 Copilot desktop add/restart recall PASS; GitHub Registry one-click install NOT VERIFIED |

This distribution does not auto-extract conversations for any MCP host. Automatic
capture and recall require a native provider or a lifecycle adapter. DSH automatic
features are opt-in; the published npm prerelease is installable, while full
live-model/Cloud and Desktop GUI acceptance remain pending.
See the [Codex validation record](docs/codex-plugin-verification.md) for the
tested CLI, source revisions and model providers; desktop GUI and native-memory
adoption are separate verification boundaries.

## Stable stdio installation

Follow the [fixed-version quickstart](docs/quickstart.md)
([中文](docs/quickstart.zh-CN.md)) for environment checks, the dedicated
profile, `init`, `doctor`, model reuse, client configuration and tool-level
write/search/reconnect verification. Complete package preparation and profile
checks in a terminal before connecting the host; the client connection must
not be used to install, download models, initialize an existing collection or
migrate data. Hermes profiles should use the native provider documented in the
[Runtime installation guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/INSTALL.md).

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
args = ["--from", "qdrant-memory-mcp==0.3.5", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"]
```

OpenCode `opencode.json` example:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "qdrant_memory": {
      "type": "local",
      "command": ["uvx", "--from", "qdrant-memory-mcp==0.3.5", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"],
      "enabled": true
    }
  }
}
```

Pi needs a separately installed MCP client/extension. In that extension, use
`command: uvx` and the same argument list. No built-in Pi MCP support or universal
extension config format is claimed. These are configuration examples. This
protocol acceptance tests use the official Python MCP SDK. Host-specific evidence
is recorded separately in the [architecture and support boundaries](docs/cross-harness-architecture.md)
and the Runtime's [client evidence and limits](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/mcp.md).

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

## Concepts and evidence

- Sharing vs Portability vs Backup: [Runtime portability guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/portability.md)
- Cross-harness architecture: [docs/cross-harness-architecture.md](docs/cross-harness-architecture.md)
- Shared Owner status: [docs/universal-owner-status.md](docs/universal-owner-status.md)
- Validation limits: [docs/dsh-validation.md](docs/dsh-validation.md)

Validation reports apply to their recorded versions, workloads and host
environments. Short protocol or cloud runs do not establish 24-hour acceptance
for a new release.

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

## Dependency boundary

The runtime dependency is only `hermes-plugin-qdrant-memory[mcp]`. The sdist includes the
Python acceptance tests, apart from harnesses that need an external Runtime checkout, DSH
client assets, or Node fixtures the sdist does not carry; selected harness lockfiles and
Node-only `.mjs` tests are excluded. The wheel remains metadata-only. Development
dependencies are declared under `[project.optional-dependencies].dev` and are not installed
for end users.

## WorkBuddy and DeepSeek Harness

Use the [WorkBuddy connector](integrations/workbuddy/README.md) or the
[DSH installation guide](docs/dsh-integration.md) for explicit durable memory.
Both reuse the Python Runtime, the four MCP tools and the canonical Skill. The published [managed launcher](integrations/managed/README.md) prepares private Python
and CPU-model dependencies with Node.js. Thus, the managed routes do not require a
system Python, uvx or Ollama installation. The DSH Bundle is
distributed as `@cnkang/qdrant-memory-dsh-bundle`. Existing Hermes profiles
and defaults are unchanged. See [architecture and version matrix](docs/cross-harness-architecture.md)
and [validation limits](docs/dsh-validation.md).
