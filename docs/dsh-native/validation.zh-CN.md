# DSH 原生适配器验证报告

[English](validation.md) · [中文](validation.zh-CN.md)

本报告区分本地合成测试、GitHub CI 和真实模型/桌面证据。某一层通过不代表更高一层也通过。

## 兼容性矩阵

| 路径 | 宿主包 | Node / 包管理器 | Runtime 契约 | 状态 |
| --- | --- | --- | --- | --- |
| 现有 MCP Bundle / Python overlay | 已发布路径和既有集成测试仍固定 DSH `0.2.1-rc.2`；旧 lockfile 与工作流保留 | 原有旧版本测试线 | 已发布的显式 MCP 工具 | 受支持路径；不自动捕获或召回轮次 |
| 原生生命周期预览 | `@deepseek-ai/dsh@0.2.2-rc.1`、`@deepseek-ai/dsh-llm@0.2.2-rc.1`、`@deepseek-ai/cordis@4.1.0`、`@deepseek-ai/schemastery@3.19.0` | Node.js `24.9.0`；Plugin Manager pnpm `11.28.5`；npm lockfile 精确锁定 | `qdrant-memory/extraction-v1` Owner 候选事件 | 源码已并入 `main`；npm 包仍为 private；Runtime 0.6.1 已并入但尚未上 PyPI（公开最新为 0.6.0） |
| DSH 浮动 `next` | 独立的既有 canary | 非阻塞工作流 | MCP 兼容性 | 不是原生功能发布就绪证据 |
| DSH Core | 上游 release commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db` | 未修改源码 | 仅使用公开 Host API | 未修改 |

原生适配器不调用 DSH MCP Client 或 Skill filesystem provider，因此不把它们列为原生直接依赖。已发布 MCP/Skill 集成保留独立的精确依赖锁和测试。agent、session 和生命周期 API 由 Cordis Host 提供；适配器直接固定其调用的 DSH CLI、LLM facade、Cordis 和 schema 包。

## 本地自动化证据（2026-11-08）

| 仓库 / 检查 | 命令 | 结果 |
| --- | --- | --- |
| 原生适配器单元 fixture | 在 `integrations/dsh/native` 运行 `npm test` | PASS：macOS Apple Silicon、Node `24.22.1` 上 19 项测试 |
| Runtime Owner 候选契约 | `pytest -q tests/standalone/test_owner_lifecycle.py tests/standalone/test_native_backlog_counter.py` | PASS：22 项测试 |
| MCP 跨 Harness 契约 | `pytest -q tests/test_cross_harness.py` | PASS：5 项测试 |
| DSH CLI profile 安装/配置/移除 | 设置隔离 `DSH_HOME` 后运行 `npm run validate:host` | 在 GitHub CI 的 Linux x64、macOS 15 arm64、Windows x64 上 PASS |
| Linux x64 / macOS Apple Silicon / Windows x64 工作流 | [`.github/workflows/dsh-native.yml`](../../.github/workflows/dsh-native.yml) | PASS：[run 42454963156](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42454963156) |
| 浮动 `next` 兼容探测 | [`.github/workflows/dsh-next.yml`](../../.github/workflows/dsh-next.yml) | PASS：[run 42454963293](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42454963293) |
| 旧 MCP Bundle / overlay 测试线 | [`.github/workflows/cross-harness.yml`](../../.github/workflows/cross-harness.yml) | PASS：[run 42454963217](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42454963217) |

原生单测用合成 DSH 事件和注入的 Owner 请求边界调用实际适配器 handler，覆盖默认关闭、输入过滤、有界注入、session 缓存隔离/清理、发送候选时不包含助手原文、基于 receipt 的 replay、fork 前缀排除、subagent 排除和 capture 超时清理。Runtime lifecycle 测试覆盖候选契约、授权边界、replacement context 校验、持久幂等性和 backlog 口径。这些不是完整 DSH AgentLoop 测试。

## 尚未验证的验收场景

在描述为生产就绪前，还需要以下证据：

- 真实 DSH AgentLoop/模型请求，证明注入文本实际到达模型并且没有改动 system prompt。
- 真实 Owner 和 embedding/Qdrant destination 的 Session A 捕获、Session B 召回。
- 基于模型的 add/update/skip/conflict 和矛盾处理；同一输入重复十次去重；删除后重启/恢复。
- 真实 Host 中的崩溃边界、fork/resume、两个并发 session、队列满、取消、后端不可用、hot reload 和完整 DSH 进程重启。
- 使用不同且未授权凭证验证 Shared Owner 拒绝访问。
- 真实 CPU embedding/Qdrant、真实模型评估和 Desktop GUI 场景。
- 进程内召回/捕获计数器之外的适配器运行指标。Runtime receipt 只返回状态，无法提供 mutation 类型拆分与 dedupe rate，生产延迟/token 测量尚未记录。
- 实测延迟与 token 数、负载下的队列恢复时限、长时间运行的内存/listener 行为。

GitHub workflow 会在三个真实架构 runner 上将包安装到临时 DSH profile、合成 config、移除插件、执行原生 fixture、校验精确 Node/DSH/pnpm 版本，并执行不发布的 pack。它不运行真实模型、Owner、Qdrant destination 或 GUI。

## 隐私、回退与发布状态

适配器向 Runtime 发送抽取候选，不发送完整助手 transcript。DSH 当前配置的模型仍会收到用于抽取的 turn 内容。不同 DSH profile 使用独立 Owner token。保留已发布 Bundle/overlay；回退时关闭三个原生开关，只移除原生插件。不要在回退期间删除 profile、Owner ledger/receipt、Qdrant collection 或 embedding cache。

发布就绪状态：**尚未就绪**。原生源码已并入，但 npm 包仍为 private 且未发布，Runtime 0.6.1 尚未上 PyPI，真实 AgentLoop/模型/GUI/CPU embedding 证据缺失。不得把 CI 或合成结果表述为真实 Host 验收。
