# DSH 原生适配器验证报告

[English](validation.md) · [中文](validation.zh-CN.md)

本报告区分本地合成测试、GitHub CI 和真实模型/桌面证据。某一层通过不代表更高一层也通过。

## 兼容性矩阵

| 路径 | 宿主包 | Node / 包管理器 | Runtime 契约 | 状态 |
| --- | --- | --- | --- | --- |
| 现有 MCP Bundle / Python overlay | 已发布路径和既有集成测试仍固定 DSH `0.2.1-rc.2`；旧 lockfile 与工作流保留 | 原有旧版本测试线 | 已发布的显式 MCP 工具 | 受支持路径；不自动捕获或召回轮次 |
| 原生生命周期预览 | `@deepseek-ai/dsh@0.2.2-rc.1`、`@deepseek-ai/dsh-llm@0.2.2-rc.1`、`@deepseek-ai/cordis@4.1.0`、`@deepseek-ai/schemastery@3.19.0` | Node.js `24.9.0`；Plugin Manager pnpm `11.28.5`；npm lockfile 精确锁定 | `qdrant-memory/extraction-v1` Owner 候选事件 | Runtime 0.6.2 已公开且是失败事件重试的最低版本；0.6.1 仅保留为手动兼容 fixture；公开 Bundle 仍为 0.1.6 |
| DSH 浮动 `next` | 独立的既有 canary | 非阻塞工作流 | MCP 兼容性 | 不是原生功能发布就绪证据 |
| DSH Core | 上游 release commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db` | 未修改源码 | 仅使用公开 Host API | 未修改 |

原生适配器不调用 DSH MCP Client 或 Skill filesystem provider，因此不把它们列为原生直接依赖。已发布 MCP/Skill 集成保留独立的精确依赖锁和测试。agent、session 和生命周期 API 由 Cordis Host 提供；适配器直接固定其调用的 DSH CLI、LLM facade、Cordis 和 schema 包。

## 当前 GitHub 证据（2026-11-13）

最新获取的 MCP `main` 为 `7571bc73a4cdd8d5059ba6cc4664b1837ee02566`。
[原生矩阵 run 43344866002](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43344866002)
的四个 Linux x64、macOS 15 ARM64、Windows x64 job 全部通过，包含 Node 24.9.0 下限，且没有 skipped 或 cancelled 步骤。
[真实 AgentLoop/Owner run 43344866057](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43344866057)
在同一 SHA 上通过，使用确定性模型和 Docker Qdrant；这是实际 Host/Owner 集成证据，但不是实际模型验收。

受保护 Cloud smoke
[43326521742](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/43326521742)
在较早的精确 MCP SHA `84ba8cb8b32679265077c1af0ff0187f04dcb480` 上通过一项配置真实 Ollama Cloud 的 case，且无 skipped 测试。它仍只是部分验收：Cloud UPDATE/CONFLICT 和 Hermes/Codex 到 DSH 的跨 Harness 验收尚未通过。npm 公开 Bundle 仍为 `0.1.6`，没有发布新候选包。

## 本地自动化证据（2026-11-08）

| 仓库 / 检查 | 命令 | 结果 |
| --- | --- | --- |
| 原生适配器单元 fixture | 在 `integrations/dsh/native` 运行 `npm test` | PASS：macOS Apple Silicon、Node `24.22.1` 上 25 项测试 |
| Runtime Owner 候选契约 | `cd ../hermes-plugin-qdrant-memory && pytest -q tests/standalone/test_owner_lifecycle.py tests/standalone/test_native_backlog_counter.py` | PASS：Runtime 仓库 25 项测试，不在本仓库运行 |
| MCP 跨 Harness 契约 | `pytest -q tests/test_cross_harness.py` | PASS：5 项测试 |
| DSH CLI profile 安装/配置/移除 | 设置隔离 `DSH_HOME` 后运行 `npm run validate:host` | 在 GitHub CI 的 Linux x64、macOS 15 arm64、Windows x64 上 PASS |
| Linux x64 / macOS Apple Silicon / Windows x64 工作流 | [`.github/workflows/dsh-native.yml`](../../.github/workflows/dsh-native.yml) | PASS：[run 42484265301](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42484265301)（代码修订 `25fe32c`） |
| 浮动 `next` 兼容探测 | [`.github/workflows/dsh-next.yml`](../../.github/workflows/dsh-next.yml) | PASS：[run 42484265261](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42484265261) |
| 旧 MCP Bundle / overlay 测试线 | [`.github/workflows/cross-harness.yml`](../../.github/workflows/cross-harness.yml) | PASS：[run 42484265269](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/42484265269) |

原生单测用合成 DSH 事件和注入的 Owner 请求边界调用实际适配器 handler，覆盖默认关闭、输入过滤、有界注入、session 缓存隔离/清理、发送候选时不包含助手原文、基于 receipt 的 replay、fork 前缀排除、subagent 排除和 capture 超时清理。Runtime lifecycle 测试覆盖候选契约、授权边界、replacement context 校验、持久幂等性和 backlog 口径。这些不是完整 DSH AgentLoop 测试。

## 尚未验证的验收场景

在描述 DSH 正式发布为生产就绪前，还需要以下证据：

- 更广泛的真实模型 AgentLoop Cloud UPDATE/CONFLICT 和跨 Harness 测试；现有真实模型 run 只覆盖一个 synthetic case。
- Desktop GUI 安装、原位升级、回退、profile 隔离及与其他记忆提供方共存。
- 重复的真实模型 add/update/skip/conflict、矛盾处理、去重和删除后恢复验收。
- 超出当前确定性 Provider 和有界恢复检查的真实 CPU embedding 评估，以及长期运行的内存/listener 测量。
- 进程内召回/捕获计数器之外的适配器运行指标。Runtime receipt 只返回状态，无法提供 mutation 类型拆分与 dedupe rate，生产延迟/token 测量尚未记录。

Required GitHub 矩阵会在临时 DSH profile 中安装插件、合成 config、移除插件、执行原生 fixture、校验精确 DSH/pnpm 版本，并在 Linux x64、macOS arm64、Windows x64 上执行不发布的 pack；其中包含 Node 24.9.0 下限。独立的 exact-main 跨客户端 CI 使用确定性 Provider 验收真实 AgentLoop、HTTPS Owner 和 Docker Qdrant。受保护 Cloud run 增加一项配置真实模型的 smoke，但两个工作流都没有覆盖完整的真实模型矩阵或 Desktop GUI。

## 隐私、回退与发布状态

适配器向 Runtime 发送抽取候选，不发送完整助手 transcript。DSH 当前配置的模型仍会收到用于抽取的 turn 内容。不同 DSH profile 使用独立 Owner token。保留已发布 Bundle/overlay；回退时关闭三个原生开关，只移除原生插件。不要在回退期间删除 profile、Owner ledger/receipt、Qdrant collection 或 embedding cache。

发布就绪状态：**尚未就绪**。Runtime 0.6.2 已公开，exact-main Native 和真实 AgentLoop/Owner 集成 CI 通过。公开 Bundle 仍为 0.1.6；受保护 Cloud 和 Desktop 验收未完成。不得把确定性 AgentLoop CI 或单项 Cloud smoke 表述为完整的真实模型或 Desktop 验收。
