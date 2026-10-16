# WorkBuddy installation

The published connector uses the managed launcher and WorkBuddy's managed
Node.js runtime. It removes the need to install Python/uvx or Ollama manually.
The connector ZIP ships one `mcp.json` that pins the exact public launcher
version. `mcp.uvx.json` documents the older Python/uvx custom-MCP route for
advanced users and is not part of the ZIP.

## How the managed connector works

WorkBuddy documents a managed Node runtime for stdio connectors from version
5.0.0. The connector declares:

```json
"command": "npx",
"args": ["-y", "@cnkang/qdrant-memory-launcher@0.1.0-rc.2", "mcp", "workbuddy", "--auto-setup"],
"runtime": {"type": "node", "version": "20"},
"npmRegistries": ["https://registry.npmjs.org", "https://registry.npmmirror.com"]
```

The Node front end promptly completes MCP initialization and exposes the four
fixed memory schemas. It then prepares dependencies in the background. Until
the Python backend is ready, tools return an explicit error. No memory write
is queued or reported successful. Dependencies, bootstrap and model files are
pinned and verified. Setup uses only the Runtime's supported CLI.

The npm registry list is an ordered fallback. The canonical registry is first.
A release cannot ship while the pinned launcher version is unavailable there
with matching integrity. The handshake budget is the connector's 30-second
timeout; measured cold handshakes stay within it on every platform (worst
observed cold npx: Windows, 15.5 seconds).

The same program installer serves DSH, but DSH preparation is explicit and
separate from its temporary MCP probe. Shared installation does not mean shared
data: each host has its own profile and agent identity. Hermes is unchanged.
See [cross-harness architecture](cross-harness-architecture.md).

## Credentials and lifecycle

The local CPU preset needs no service account or API key. Download/install
processes receive no service credentials. Optional Cloud configuration remains
on the existing Python path. The managed connector does not provide a Cloud
credential-form preset or certify multi-writer sharing.

Disconnect closes Python stdin, then escalates termination if necessary. A
backend crash closes the bridge so WorkBuddy can reconnect. No write is
automatically replayed. Installation failures are explicit and retryable. A
force-killed installer may require operator inspection of its installation lock.
Never remove Runtime data locks or reset a profile to bypass ownership.

Program/dependency changes install alongside earlier versions. Profile, ledger
and collection files remain in place. Incompatible data must fail closed.

## Release boundary

The Runtime wheel and the canonical Skill pins are public artifacts. The
launcher pin (`0.1.0-rc.2`) must be published before release assets are
prepared; the release workflow refuses unpublished pins, and the public
acceptance records `NOT VERIFIED` until the version is available. The
connector pins each artifact exactly. Marketplace ZIP import and managed-Node
GUI acceptance remain maintainer gates before marketplace submission; the
repository records only measured, reproducible acceptance. Do not advertise
marketplace one-click support before those gates pass. Do not replace published
tags.
