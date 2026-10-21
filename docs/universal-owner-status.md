# Universal Owner capabilities and limits (source preview)

[简体中文](universal-owner-status.zh-CN.md)

This page describes source preview capabilities and support limits.
The released distribution uses Runtime 0.4.0.
Preview features require a separate installation of reviewed Runtime source with the applicable interfaces.
The source preview does not establish production acceptance.

## Capabilities

| Capability | Support limits |
|---|---|
| One Owner, multiple clients | Clients share one Runtime, Ledger, compare-and-swap (CAS), receipts, and recovery mechanism. MCP tests use separate processes to verify these boundaries. |
| Hermes Native Owner | Hermes uses the same Provider, Runtime, and host model. Only explicitly approved rules can automatically save records to a project space. |
| HTTPS Streamable HTTP | The gateway uses the official Python SDK and listens on a loopback address. This configuration uses a TLS proxy on the same host. Tests use two containers to verify TLS and network separation. |
| Private memory across devices for one agent | Separate principals, devices, and tokens map to the same logical agent. Existing private records do not migrate automatically. |
| Pi automatic memory | The adapter uses official Pi 1.3.0 lifecycle hooks. The Owner extracts and persists memories. Tests use real Pi sessions and deterministic models. |
| Hermes-to-Pi automatic handoff | Tests use actual Hermes MemoryManager callbacks, one Owner, verified HTTPS, and a fresh session in a separate Pi process. |
| Codex, DSH, WorkBuddy, OpenCode | These hosts support explicit MCP or assisted use. Automatic memory requires a separate, verified lifecycle adapter for each host. |
| OAuth, OIDC, browser authentication | The source preview does not support these authentication methods. Each client uses a separate service credential configured in advance. |
| Embedded, Server, Cloud | All three deployment modes remain available. Validation covers Embedded and Server with TLS/JWT. A separate Runtime Cloud Owner test passed and removed its test collection. Collection-level credential restrictions remain unverified. |
| Model quality | Runtime CI uses Qwen3.5 0.8B for functional smoke tests. A smoke pass does not establish extraction quality. Validate the target model with the full quality suite before deployment. |

## Pi sessions and authorization

Pi replays only this extension's pending events from the current authorized session.
Retries use the same event IDs.
Each event binds to the Owner URL and a digest of the capture credential.
A different Owner or credential does not automatically send old events to a new space.
After credential rotation, the administrator must explicitly handle old events that remain unsent.
The digest does not contain a usable plaintext token.

The adapter requests shared recall through the temporary `context` hook for each model request.
It marks recall as untrusted data and retains provenance, space, and version information.
It does not reuse old recall after request failures, access denials, record deletion, or permission revocation.
It does not save shared recall in session history.
Capture and read-only recall credentials can have separate scopes and independent revocation.
The Owner controls identity, permissions, and space selection.

## Validation and deployment limits

[Pi configuration and tests](../integrations/pi/README.md) describe hook tests, real Pi session tests, and Hermes-to-Pi HTTPS tests.
These tests use deterministic model and embedding fixtures.
They do not verify production model quality, host user interfaces, or public network deployment.
Each host requires separate acceptance evidence.

The [Runtime Cloud Owner test](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/39558088367)
passed 11 tests on main.
The test removed its records and collection, and a separate cleanup check confirmed removal.
It used a test API key, so it does not establish collection-level credential isolation.
The [Runtime model guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/model-quality.md)
distinguishes functional smoke results from full model quality results.
These Runtime results do not establish production acceptance or host UI acceptance.

The released distribution adopts a new Runtime version only after compatibility validation.
The source preview does not automatically migrate user data or change production services.
[Shared service configuration](../integrations/shared/README.md) describes separate credentials and HTTPS examples.
Read [deployment security](shared-deployment-security.md) before deployment.
