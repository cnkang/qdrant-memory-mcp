# 在 DeepSeek Harness 中使用 Qdrant 长期记忆

通过 DSH 官方 MCP 客户端，可以搜索、保存、更新和删除长期记忆。
它提供明确的记忆操作，不会自动保存每一轮对话。

[English](dsh-integration.md) · [验证范围](dsh-validation.md)

## 使用已发布的 Python 服务

需要 Python 3.11+、uv/uvx 和可用的嵌入服务（例如 Ollama）。按照
[快速入门](quickstart.zh-CN.md) 配置，但把 profile 改为独立的
`~/.qdrant-memory-dsh`，在其中创建 `qdrant-memory.json`，设置身份、模型和服务地址。
然后执行：

```sh
uvx --from qdrant-memory-mcp==0.1.3 qdrant-memory-mcp --home "$HOME/.qdrant-memory-dsh" init
uvx --from qdrant-memory-mcp==0.1.3 qdrant-memory-mcp --home "$HOME/.qdrant-memory-dsh" doctor
dsh web --patch /绝对路径/qdrant-memory-mcp/integrations/dsh/qdrant-memory.cordis.yml
```

Windows 请使用对应的绝对路径。启动 DSH 前可用环境变量
`QDRANT_MEMORY_DSH_PROFILE` 指定其他独立 profile。不要选择正在使用的
Hermes 或 WorkBuddy 数据目录。启用 overlay 前先完成依赖准备；DSH 不会替第三方
MCP 服务安装软件、选择模型或初始化数据库。

overlay 只为本次启动添加一个独立插件，不覆盖 `cordis.patch.yml`，不修改默认
Profile。需要长期启用时，可保留 `--patch` 参数，或把单个 `insert` 条目合并到
选定 profile 的现有 patch 中。不要直接覆盖原文件，也不要同时启用 Python 和托管
两个 overlay。其他 profile 不受影响。

也可以通过 DSH 官方插件安装命令，把[纯配置 Bundle](../integrations/dsh/README.md)
安装到选定 profile。它用合法的 `dsh.bundle.patch` 添加同一条 MCP 配置，仍需先准备
后端；不要与 overlay 重复启用。

默认工具名是 `mcp__qdrant-memory__qdrant_memory_search`，以及同前缀的
`add`、`update`、`delete`。改动 `serverName` 后请以实际发现的工具名为准。
原始工具参数和 scope 限制保持不变；继续使用 DSH 自身的工具授权机制。

## 安装共用 Skill

唯一权威来源是 [cnkang/skills 的 qdrant-memory](https://github.com/cnkang/skills/tree/main/qdrant-memory)。
把整个目录及其 references 安装到项目的 `.agents/skills/qdrant-memory`，或者用
DSH 的 `customSkillDirs` 指向包含该目录的已审核 checkout。支持符号链接的系统
可以链接到权威 checkout。DSH 会识别 `qdrant-memory/SKILL.md`，无需维护另一套
DSH 专用 Skill。若多个目录已有同名 Skill，请选定一个版本，避免重复来源。

## 可选：托管 CPU 模型候选方案

此方案需要 Node.js 20+ 和网络，会准备私有 Python 环境及经过校验的 CPU 模型，
无需预装 Python、uvx 或 Ollama。目前提供源码候选版，尚未发布 npm 包或市场连接器。
请先手动准备，再连接 DSH：

```sh
node /绝对路径/integrations/managed/launcher.mjs prepare dsh
export QDRANT_MEMORY_LAUNCHER=/绝对路径/integrations/managed/launcher.mjs
dsh web --patch /绝对路径/integrations/dsh/managed.cordis.yml
```

下载可能需要数分钟，等待输出 `{"ready":true,"host":"dsh"}` 后再继续。
DSH 的临时探测进程只连接已准备好的服务，不会执行安装。托管方案的数据目录与
上述 Python 方案分开，详见[启动器说明](../integrations/managed/README.md)。

## 凭证、重试与数据保护

DSH 会清理继承环境中名称包含 KEY、PASSWORD、SECRET、TOKEN 的变量以及
`DSH_*` 变量。Python overlay 已通过 `!!js process.env` 显式转发
`QDRANT_API_KEY` 和 `EMBEDDING_API_KEY`。请用可信 shell 或凭证管理器设置值，
不要把真实凭证写进 YAML、命令参数、Skill、对话或日志。若 profile 使用其他
凭证变量，需显式增加对应转发。仅无须认证的服务可以使用空值。托管 CPU 方案无需密钥。

工具提示准备中或准备失败时，表示没有成功执行操作。先修复安装问题，再重试；
不要用无限重连掩盖安装失败。已派发的写操作中断后，先搜索确认结果再决定是否重试。
数据目录被占用时，正常关闭原连接；不要删锁、重置数据库或修改 fingerprint 强行启动。

关闭本次 overlay 或禁用选定 profile 中的插件即可断开，磁盘数据会保留。
验收时在会话 A 保存合成事实，在不传入旧对话的会话 B 检索并使用；再按返回的 ID
更新和删除，并完整重启 DSH 验证持久化。自动化官方客户端测试与真实模型/GUI
会话验收分别记录，不相互替代。
