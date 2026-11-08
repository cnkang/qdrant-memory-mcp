# DSH native adapter validation

[English](validation.md) · [中文](validation.zh-CN.md)

This report separates local fixtures, GitHub CI, and real-model/desktop evidence. A passing layer does not establish the next layer.

## Compatibility matrix

| Path | Host packages | Node / package manager | Runtime contract | Status |
| --- | --- | --- | --- | --- |
| Existing MCP Bundle / Python overlay | The published and integration-test lane remains on DSH `0.2.1-rc.2`; legacy package locks and workflows are retained | Existing legacy lane | Published explicit MCP tools | Supported route; no automatic turn capture or recall |
| Native lifecycle preview | `@deepseek-ai/dsh@0.2.2-rc.1`, `@deepseek-ai/dsh-llm@0.2.2-rc.1`, `@deepseek-ai/cordis@4.1.0`, `@deepseek-ai/schemastery@3.19.0` | Node.js `24.9.0`; Plugin Manager pnpm `11.28.5`; exact npm lockfile | `qdrant-memory/extraction-v1` Owner candidate event | Source merged to `main`; npm package remains private; Runtime 0.6.1 is merged but not yet on PyPI (latest published is 0.6.0) |
| DSH floating `next` | Separate existing canary | Non-blocking workflow | MCP compatibility | Not evidence for native release readiness |
| DSH Core | Upstream release commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db` | No source change | Public Host APIs only | Not modified |

The native adapter does not call the DSH MCP Client or Skill filesystem provider, so neither is a direct native dependency. The separate published MCP/Skill integration retains its own exact package lock and tests. DSH supplies the agent, session, and lifecycle APIs to the Cordis plugin; the adapter directly pins the DSH CLI, LLM facade, Cordis, and schema package it uses.

## Local automated evidence (2026-11-08)

| Repository / check | Command | Result |
| --- | --- | --- |
| Native adapter unit fixtures | `npm test` in `integrations/dsh/native` | PASS: 20 tests on macOS Apple Silicon, Node `24.22.1` |
| Runtime Owner candidate contract | `pytest -q tests/standalone/test_owner_lifecycle.py tests/standalone/test_native_backlog_counter.py` | PASS: 22 tests |
| MCP cross-harness contract | `pytest -q tests/test_cross_harness.py` | PASS: 5 tests |
| DSH CLI profile install/config/remove | `npm run validate:host` with isolated `DSH_HOME` | PASS in GitHub CI on Linux x64, macOS 15 arm64, Windows x64 |
| Linux x64 / macOS Apple Silicon / Windows x64 workflow | [`.github/workflows/dsh-native.yml`](../../.github/workflows/dsh-native.yml) | PASS: [run 42456569756](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42456569756) (code revision `32c9e85`) |
| Floating `next` compatibility probe | [`.github/workflows/dsh-next.yml`](../../.github/workflows/dsh-next.yml) | PASS: [run 42456569792](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42456569792) |
| Legacy MCP Bundle / overlay lane | [`.github/workflows/cross-harness.yml`](../../.github/workflows/cross-harness.yml) | PASS: [run 42456569740](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42456569740) |

The native unit fixtures call the actual adapter handlers with synthetic DSH events and an injected Owner request boundary. They verify default-off behavior, filtering, bounded injection, session-local cache cleanup, candidate payload omission of raw assistant text, receipt-based replay, fork-prefix exclusion, subagent exclusion, and capture
timeout cleanup. The Runtime lifecycle tests verify the candidate contract, authorization boundary, replacement-context validation, durable idempotence, and backlog accounting. These are not full DSH AgentLoop tests.

## Unverified acceptance scenarios

The following need additional evidence before describing native capture/recall as production-ready:

- Real DSH AgentLoop/model request proving injected text reached the model and did not alter the system prompt.
- Session A capture followed by Session B recall from a real Owner and embedding/Qdrant destination.
- Model-based add/update/skip/conflict and contradiction handling; ten-repeat dedupe; deletion followed by restart/recovery.
- Crash boundaries, fork/resume behavior in a real host, two live sessions, queue overflow, cancellation, backend outage, hot reload, and complete DSH process restart.
- Shared Owner denial using separate, non-authorized credentials.
- Real CPU embedding and Qdrant test, real model evaluation, and all Desktop GUI scenarios.
- Adapter operational metrics beyond in-process recall/capture counters. Runtime receipts return status only, so mutation action breakdown and dedupe rate are unavailable, and production latency/token measurements are not recorded.
- Measured latency, token counts, queue recovery horizon under load, and long-running memory/listener behavior.

The GitHub workflow installs the package into a disposable DSH profile, composes its config, removes it, runs native fixtures, checks exact Node/DSH/pnpm versions, and packs without publishing across the three real-architecture runners. It does not run a real model, Owner, Qdrant destination, or GUI.

## Privacy, rollback, and release state

The adapter sends extracted candidates, not raw assistant transcript, to Runtime. DSH's configured model still receives the turn content for extraction. Use a dedicated Owner token for each unrelated DSH profile. Keep the published Bundle/overlay path available; rollback disables the three native switches and removes only the native plugin. Do not delete the profile, Owner ledger/receipts, Qdrant collection, or embedding cache during rollback.

Release readiness: **not ready**. The native source is merged, but the npm package is private and unpublished, Runtime 0.6.1 is not yet on PyPI, and real AgentLoop/model/GUI/CPU embedding evidence is absent. Do not convert a synthetic or CI result into a real-host acceptance claim.
