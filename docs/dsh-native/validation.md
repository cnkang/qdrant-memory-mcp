# DSH native adapter validation

[English](validation.md) · [中文](validation.zh-CN.md)

This report separates local fixtures, GitHub CI, and real-model/desktop evidence. A passing layer does not establish the next layer.

## Compatibility matrix

| Path | Host packages | Node / package manager | Runtime contract | Status |
| --- | --- | --- | --- | --- |
| Existing MCP Bundle / Python overlay | The published and integration-test lane remains on DSH `0.2.1-rc.2`; legacy package locks and workflows are retained | Existing legacy lane | Published explicit MCP tools | Supported route; no automatic turn capture or recall |
| Native lifecycle preview | `@deepseek-ai/dsh@0.2.2-rc.1`, `@deepseek-ai/dsh-llm@0.2.2-rc.1`, `@deepseek-ai/cordis@4.1.0`, `@deepseek-ai/schemastery@3.19.0` | Node.js `24.9.0`; Plugin Manager pnpm `11.28.5`; exact npm lockfile | `qdrant-memory/extraction-v1` Owner candidate event | Runtime 0.6.2 is public and required for failed-event retry; 0.6.1 remains only a manual compatibility fixture; public npm bundle remains 0.1.6 |
| DSH floating `next` | Separate existing canary | Non-blocking workflow | MCP compatibility | Not evidence for native release readiness |
| DSH Core | Upstream release commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db` | No source change | Public Host APIs only | Not modified |

The native adapter does not call the DSH MCP Client or Skill filesystem provider, so neither is a direct native dependency. The separate published MCP/Skill integration retains its own exact package lock and tests. DSH supplies the agent, session, and lifecycle APIs to the Cordis plugin; the adapter directly pins the DSH CLI, LLM facade, Cordis, and schema package it uses.

## Current GitHub evidence (2026-11-13)

Latest fetched MCP `main` is `7571bc73a4cdd8d5059ba6cc4664b1837ee02566`.
[Native matrix run 43344866002](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43344866002)
passed all four Linux x64, macOS 15 ARM64, and Windows x64 jobs, including the
Node 24.9.0 floor, with no skipped or cancelled steps.
[Real AgentLoop/Owner run 43344866057](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43344866057)
passed on the same exact SHA with a deterministic model and Docker Qdrant; it
is real Host/Owner integration evidence, not real-model evidence.

The protected Cloud smoke
[43326521742](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43326521742)
passed one configured Ollama Cloud case on older exact MCP SHA
`84ba8cb8b32679265077c1af0ff0187f04dcb480`, with zero skipped tests. It remains
partial: Cloud UPDATE/CONFLICT and Hermes/Codex-to-DSH acceptance have not
passed. Public npm still serves Bundle `0.1.6`; no new candidate is published.

## Local automated evidence (2026-11-08)

| Repository / check | Command | Result |
| --- | --- | --- |
| Native adapter unit fixtures | `npm test` in `integrations/dsh/native` | PASS: 25 tests on macOS Apple Silicon, Node `24.22.1` |
| Runtime Owner candidate contract | `cd ../hermes-plugin-qdrant-memory && pytest -q tests/standalone/test_owner_lifecycle.py tests/standalone/test_native_backlog_counter.py` | PASS: 25 tests in the Runtime repository, not in this repo |
| MCP cross-harness contract | `pytest -q tests/test_cross_harness.py` | PASS: 5 tests |
| DSH CLI profile install/config/remove | `npm run validate:host` with isolated `DSH_HOME` | PASS in GitHub CI on Linux x64, macOS 15 arm64, Windows x64 |
| Linux x64 / macOS Apple Silicon / Windows x64 workflow | [`.github/workflows/dsh-native.yml`](../../.github/workflows/dsh-native.yml) | PASS: [run 42484265301](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42484265301) (code revision `25fe32c`) |
| Floating `next` compatibility probe | [`.github/workflows/dsh-next.yml`](../../.github/workflows/dsh-next.yml) | PASS: [run 42484265261](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42484265261) |
| Legacy MCP Bundle / overlay lane | [`.github/workflows/cross-harness.yml`](../../.github/workflows/cross-harness.yml) | PASS: [run 42484265269](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42484265269) |

The native unit fixtures call the actual adapter handlers with synthetic DSH events and an injected Owner request boundary. They verify default-off behavior, filtering, bounded injection, session-local cache cleanup, candidate payload omission of raw assistant text, receipt-based replay, fork-prefix exclusion, subagent exclusion, and capture
timeout cleanup. The Runtime lifecycle tests verify the candidate contract, authorization boundary, replacement-context validation, durable idempotence, and backlog accounting. These are not full DSH AgentLoop tests.

## Unverified acceptance scenarios

The following still need additional evidence before describing the DSH release as production-ready:

- Broader real-model AgentLoop coverage of Cloud UPDATE/CONFLICT and cross-harness paths; the passing configured-model run covers one synthetic case.
- Full Desktop GUI install, in-place upgrade, rollback, profile isolation, and coexistence with other memory providers.
- Repeated real-model add/update/skip/conflict, contradiction handling, deduplication, and deletion/recovery cases.
- Real CPU embedding evaluation and long-running memory/listener measurements beyond the current deterministic-provider and bounded-recovery checks.
- Adapter operational metrics beyond in-process recall/capture counters. Runtime receipts return status only, so mutation action breakdown and dedupe rate are unavailable, and production latency/token measurements are not recorded.

The required GitHub matrix installs the package into a disposable DSH profile, composes its config, removes it, runs native fixtures, checks exact DSH/pnpm versions, and packs without publishing across Linux x64, macOS arm64, Windows x64, plus the declared Node 24.9.0 floor. Separate exact-main cross-client CI exercises the real AgentLoop, HTTPS Owner, and Docker Qdrant with a deterministic Provider. The protected Cloud run adds one configured real-model smoke, but neither workflow covers the full live-model matrix or Desktop GUI.

## Privacy, rollback, and release state

The adapter sends extracted candidates, not raw assistant transcript, to Runtime. DSH's configured model still receives the turn content for extraction. Use a dedicated Owner token for each unrelated DSH profile. Keep the published Bundle/overlay path available; rollback disables the three native switches and removes only the native plugin. Do not delete the profile, Owner ledger/receipts, Qdrant collection, or embedding cache during rollback.

Release readiness: **not ready**. Runtime 0.6.2 is public, and exact-main Native plus real AgentLoop/Owner integration CI pass. The public Bundle remains 0.1.6; protected Cloud and Desktop acceptance are incomplete. Do not convert deterministic AgentLoop CI or the single Cloud smoke into full real-model or Desktop acceptance.
