# WorkBuddy installation options

The published connector uses Python/uvx and a separately initialized memory
profile. For that path, follow the [connector guide](../integrations/workbuddy/README.md).

An optional [managed source candidate](../integrations/managed/README.md) uses
Node.js to prepare a private Python environment, the shared Runtime and a
verified CPU embedding model. This removes the need to install Python/uvx or
Ollama manually. The candidate is available for custom-connection testing.
Marketplace one-click installation is not yet released or certified.

## How the managed candidate works

WorkBuddy documents a managed Node runtime for stdio connectors from version
5.0.0. The source preview's configuration uses this declaration. Native GUI
acceptance also distinguishes a user-supplied Node executable from WorkBuddy's
managed Node installation. See the [official connector specification](https://open.workbuddy.cn/docs/connector).

The Node front end promptly completes MCP initialization and exposes the four
fixed memory schemas. It then prepares dependencies in the background. Until
the Python backend is ready, tools return an explicit error. No memory write is
queued or reported successful. Dependencies, bootstrap and model files are pinned
and verified. Setup uses only the Runtime's supported CLI.

The same program installer serves DSH, but DSH preparation is explicit and
separate from its temporary MCP probe. Shared installation does not mean shared
data: each host has its own profile and agent identity. Hermes is unchanged.
See [cross-harness architecture](cross-harness-architecture.md).

## Credentials and lifecycle

The local CPU candidate needs no service account or API key. Download/install
processes receive no service credentials. Optional Cloud configuration remains
on the existing Python path. The managed source candidate does not provide a
Cloud credential-form preset or certify multi-writer sharing.

Disconnect closes Python stdin, then escalates termination if necessary. A
backend crash closes the bridge so WorkBuddy can reconnect. No write is
automatically replayed. Installation failures are explicit and retryable. A
force-killed installer may require operator inspection of its installation lock.
Never remove Runtime data locks or reset a profile to bypass ownership.

Program/dependency changes install alongside earlier versions. Profile, ledger
and collection files remain in place. Incompatible data must fail closed.
Upgrade/rollback acceptance is still required before a production release.

## Release boundary

Retain the published connector until the [release checklist](workbuddy-one-click-validation.md)
passes. Publish shared Runtime/setup APIs first, then the launcher, then a
connector pinned to those released artifacts and the canonical Skill commit.
Do not replace published tags or advertise marketplace one-click support based
on custom-connection GUI acceptance.
