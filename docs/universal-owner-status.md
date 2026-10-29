# Universal Owner capabilities and limits

[简体中文](universal-owner-status.zh-CN.md)

This page describes Runtime 0.5.2 capabilities and the repository's preview adapters.
Distribution 0.2.6 selects the published Runtime 0.5.2 package.
Preview adapters require a separate installation of the applicable integration.
Publication and source CI do not establish production acceptance.

Current Owner source CI pins Runtime [`f4aa663f750b9cb306d00231a0a2085df60d8f92`](https://github.com/cnkang/hermes-plugin-qdrant-memory/tree/f4aa663f750b9cb306d00231a0a2085df60d8f92), the published Runtime 0.5.2 source.

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
| OAuth, OIDC, browser authentication | This release does not support these authentication methods. Each client uses a separate service credential configured in advance. |
| Embedded, Server, Cloud | All three deployment modes remain available. Validation covers Embedded and Server with TLS/JWT. A separate Runtime Cloud Owner test passed and removed its test collection. Collection-level credential restrictions remain unverified. |
| Model quality | Runtime CI uses fixed models for functional smoke tests. A smoke pass does not establish extraction quality. Validate the target model with the full quality suite before deployment. |

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

The [Runtime Cloud Owner test](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/39691871575)
passed one end-to-end test on main, with no skipped tests.
The run used Runtime [24f9b1110ee99237f432afefbc7af7573bfae494](https://github.com/cnkang/hermes-plugin-qdrant-memory/tree/24f9b1110ee99237f432afefbc7af7573bfae494). This is a historical test baseline.
The test removed its records and collection, and a separate cleanup check confirmed removal.
It used a test API key, so it does not establish collection-level credential isolation.
The [Runtime model guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/model-quality.md)
distinguishes functional smoke results from full model quality results.
These Runtime results do not establish production acceptance or host UI acceptance.

## Manual desktop acceptance (2026-10-22)

A separate manual test used WorkBuddy 5.8.3 and DeepSeek Harness 0.2.1-rc.2.
Both applications connected through `shared-mcp` to one isolated loopback Owner.
Each application had a separate credential. The test used only synthetic records,
Embedded Qdrant, and an existing local `qwen3-embedding:4b` model with 2560 dimensions.
The tested Runtime revision was [7994e54de83fa8d39e566724dd88dd13b34970ee](https://github.com/cnkang/hermes-plugin-qdrant-memory/tree/7994e54de83fa8d39e566724dd88dd13b34970ee).
These results apply to that test baseline. The new source pin needs separate CI evidence.

| Manual check | Result |
|---|---|
| WorkBuddy add and search | PASS. The tool returned one record and its version. |
| DSH recall in an independent session | PASS. The ID, version, and creator matched. |
| DSH CAS update and identical request replay | PASS. The replay returned the same new version. Only one record remained. |
| WorkBuddy update with the old version | PASS. `SharedConflictError` rejected the write. The DSH update remained intact. |
| Owner stop and restart | PASS. DSH read the same ID, new version, content, and updater. |
| Cleanup | PASS. DSH deleted only the test record. Both applications then returned no records. A storage check confirmed zero points. |

The test restored WorkBuddy's prior custom MCP configuration, disabled the temporary
DSH bundle, stopped the Owner, and removed the temporary credentials and policy.
The empty local test profile and its synthetic operation Ledger remain for audit.
This test does not establish cross-device HTTPS UI acceptance, application restart
acceptance, native bundle installation acceptance, or automatic memory lifecycle support.
It is separate from the deterministic CI tests above.

The released distribution adopts a new Runtime version only after compatibility validation.
This release does not automatically migrate user data or change production services.
[Shared service configuration](../integrations/shared/README.md) describes separate credentials and HTTPS examples.
Read [deployment security](shared-deployment-security.md) before deployment.
