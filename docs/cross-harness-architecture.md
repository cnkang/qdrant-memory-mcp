# One memory core, three host integrations

Qdrant Memory uses one Python Runtime for embeddings, Qdrant storage, identity,
scope, WriterLease, ledger and recovery. Hermes uses it through its native
plugin. WorkBuddy and DeepSeek Harness (DSH) use the same four explicit MCP tools.
The [canonical Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory)
provides shared instructions and host-specific references.

```mermaid
flowchart TD
  R[Shared Python Runtime] --> H[Hermes native plugin]
  R --> M[Python stdio MCP]
  M --> W[WorkBuddy adapter]
  M --> D[Official DSH MCP client]
  L[Optional managed Python and model preparation] --> M
  S[Canonical Skill] --> H
  S --> W
  S --> D
```

The published Node launcher provisions a private Python environment and verified
CPU embedding model, then forwards requests to the Python server. It does not
implement memory operations or write directly to storage. It shares program
and read-only model files between WorkBuddy and DSH, with separate data profiles.
Its tool catalogue is checked against the Runtime before enabling operations.

See the [Python-versus-Node decision](adr/0001-python-runtime-and-node-launcher.md):
Node improves installation on supported hosts. It does not replace the shared
Python memory engine or require existing Python users to migrate.

WorkBuddy owns its connector metadata, managed Node declaration, connection
timeout and credential form. Its managed connection prepares the backend after
the MCP handshake. Tools report preparation errors until ready. Writes are never
queued during installation. DSH uses a separate preparation step, so its
temporary probe, reconnect and plugin unload do not run installers. Its overlay
uses the official MCP client and preserves the host's tool permissions,
cancellation and reconnect policy. Hermes lifecycle remains native.

## Profiles and sharing

| Interface | Default memory location |
| --- | --- |
| Hermes | Existing Hermes profile. Unchanged |
| Published standalone MCP | `~/.qdrant-memory`. Unchanged |
| DSH Python overlay | `~/.qdrant-memory-dsh` |
| Managed WorkBuddy | `<managed-root>/profiles/workbuddy/local` |
| Managed DSH | `<managed-root>/profiles/dsh/local` |

The managed root is `~/Library/Application Support/qdrant-memory-managed` on
macOS, `%LOCALAPPDATA%/qdrant-memory-managed` on Windows, and
`${XDG_DATA_HOME:-~/.local/share}/qdrant-memory-managed` on Linux.
`QDRANT_MEMORY_MANAGED_ROOT` can select an explicit absolute root for isolated
testing. It never redirects Hermes or the published standalone default.

Cross-host sharing is an explicit operator operation. Do not open an embedded
directory concurrently, even for reads. Local WriterLease protects one profile.
It does not coordinate separate ledgers on different machines. Remote Qdrant
also requires compatible collection identity, scope, embedding fingerprint and
one supported ledger owner. Multi-writer cloud sharing is not certified here.
Never remove locks or change fingerprints to force compatibility.

## Versions and availability

| Component | Pin | Availability |
| --- | --- | --- |
| Python MCP | 0.1.4 | Python/uvx distribution. Confirm the exact version on PyPI |
| Runtime | 0.3.0 | Public PyPI wheel. Optional CPU provider |
| Node launcher | 0.1.0-rc.2 | Release candidate pinned by the connector and Bundle. `0.1.0-rc.1` already public on npm |
| DSH bundle | 0.1.1 | Configuration-only npm bundle. It installs the launcher through the official MCP client |
| Bootstrap | uv 0.13.1 / Python 3.11.15 | Fixed platform artifacts, verified uv hash |
| Canonical Skill | 0.2.6 | See connector `skill-source.json` for exact commit |
| DSH contract-test packages | 0.2.1-rc.2 | Exact npm test pins and lockfile |

The managed installer verifies its uv executable and public Runtime wheel
before execution. uv verifies its managed Python artifacts. Runtime verifies
the CPU model files. Python dependencies are version and hash locked, and
installed as wheels without source builds. Program
directories include the lock digest, so dependency changes cannot silently reuse
another environment. Existing profiles retain their model-cache settings across
program upgrades. Native platform automation and Marketplace/real-host acceptance
are separate gates. A release candidate is not a Marketplace acceptance claim.

Publish compatible shared components first, then pin adapters independently.
No existing Hermes user needs to upgrade for these opt-in adapters.

## Native DSH plugin decision

This release defers a native Cordis memory plugin. MCP plus the canonical Skill
already supports explicit durable memory without duplicating the storage engine.
Automatic extraction, prefetch and per-session injection would require separate
user controls and tested Cordis lifecycle integration. They are future work,
not features supplied by this MCP connection. A future plugin must use supported
Runtime interfaces, effect-scoped cleanup and host authorization. It must not
replace AgentLoop or alter Hermes `sync_turn()` / `prefetch()`.
