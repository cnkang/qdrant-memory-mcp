# DSH native adapter validation

[English](validation.md) · [中文](validation.zh-CN.md)

This report separates local fixtures, GitHub CI, and real-model/desktop evidence. A passing layer does not establish the next layer.

## Compatibility matrix

| Path | Host packages | Node / package manager | Runtime contract | Status |
| --- | --- | --- | --- | --- |
| Existing MCP Bundle / Python overlay | The published and integration-test lane remains on DSH `0.2.1-rc.2`; legacy package locks and workflows are retained | Existing legacy lane | Published explicit MCP tools | Supported route; no automatic turn capture or recall |
| Native lifecycle preview | `@deepseek-ai/dsh@0.2.2-rc.1`, `@deepseek-ai/dsh-llm@0.2.2-rc.1`, `@deepseek-ai/cordis@4.1.0`, `@deepseek-ai/schemastery@3.19.0` | Node.js `24.9.0`; Plugin Manager pnpm `11.28.5`; exact npm lockfile | `qdrant-memory/extraction-v1` Owner candidate event | Unpublished preview; companion Runtime change is not yet released |
| DSH floating `next` | Separate existing canary | Non-blocking workflow | MCP compatibility | Not evidence for native release readiness |
| DSH Core | Upstream release commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db` | No source change | Public Host APIs only | Not modified |

The native adapter does not call the DSH MCP Client or Skill filesystem provider, so neither is a direct native dependency. The separate published MCP/Skill integration retains its own exact package lock and tests. DSH supplies the agent, session, and lifecycle APIs to the Cordis plugin; the adapter directly pins the DSH CLI, LLM facade, Cordis, and schema package it uses.

## Local automated evidence (2026-11-06)

| Repository / check | Command | Result |
| --- | --- | --- |
| Native adapter unit fixtures | `npm test` in `integrations/dsh/native` | PASS: 10 tests on macOS Apple Silicon, Node `22.23.2`; this local Node is below DSH's declared minimum and only supports the synthetic unit run |
| Runtime Owner candidate contract | `uv run --frozen --group test pytest tests/standalone/test_owner_lifecycle.py -q` | PASS: 12 tests |
| MCP cross-harness contract | `uv run --frozen --with pytest --with ruamel.yaml pytest tests/test_cross_harness.py -q` | PASS: 4 tests |
| DSH CLI profile install/config/remove | `npm run validate:host` with isolated `DSH_HOME` | PENDING: exact Node/pnpm requirement is enforced in GitHub CI; no user profile was touched locally |
| Linux x64 / macOS Apple Silicon / Windows x64 workflow | [`.github/workflows/dsh-native.yml`](../../.github/workflows/dsh-native.yml) | PENDING until jobs finish for the pushed commit |

The native unit fixtures call the actual adapter handlers with synthetic DSH events and an injected Owner request boundary. They verify default-off behavior, filtering, bounded injection, session-local cache cleanup, candidate payload omission of raw assistant text, and receipt-based replay. The Runtime lifecycle tests verify the new candidate contract, authorization boundary, replacement context validation, and durable idempotence. These are not full DSH AgentLoop tests.

## Unverified acceptance scenarios

The following need additional evidence before describing native capture/recall as production-ready:

- Real DSH AgentLoop/model request proving injected text reached the model and did not alter the system prompt.
- Session A capture followed by Session B recall from a real Owner and embedding/Qdrant destination.
- Model-based add/update/skip/conflict and contradiction handling; ten-repeat dedupe; deletion followed by restart/recovery.
- Crash boundaries, fork/resume behavior, two live sessions, queue overflow, cancellation, backend outage, hot reload, and complete DSH process restart.
- Shared Owner denial using separate, non-authorized credentials.
- Real CPU embedding and Qdrant test, real model evaluation, and all Desktop GUI scenarios.
- Adapter operational metrics from the Runtime receipt/ledger, including mutation action breakdown and dedupe rate. The current receipt API returns status only, and the native adapter does not fabricate those values.
- Measured latency, token counts, queue recovery horizon under load, and long-running memory/listener behavior.

The new GitHub workflow installs the package into a disposable DSH profile, composes its config, removes it, runs native fixtures, checks exact Node/DSH/pnpm versions, and packs without publishing across the three real-architecture runners. It does not run a real model, Owner, Qdrant destination, or GUI. Its status remains PENDING until GitHub reports completion.

## Privacy, rollback, and release state

The adapter sends extracted candidates, not raw assistant transcript, to Runtime. DSH's configured model still receives the turn content for extraction. Use a dedicated Owner token for each unrelated DSH profile. Keep the published Bundle/overlay path available; rollback disables the three native switches and removes only the native plugin. Do not delete the profile, Owner ledger/receipts, Qdrant collection, or embedding cache during rollback.

Release readiness: **not ready**. The package is private and unpublished, the compatible Runtime change is not published, host-level CI is pending, and real AgentLoop/model/GUI/CPU embedding evidence is absent. Do not convert any pending or synthetic result into a real-host acceptance claim.
