# Qdrant Memory for Codex

**One Memory. Multiple Agents. No Lock-in. 一份记忆，多个 Agent，自由迁移。**

使用现有 Qdrant Runtime，提供显式搜索、新增、更新、删除，以及 Codex v1/v2
语义记忆只读导入、可验证的 JSON/Markdown 导出。退出后无需插件即可读取数据。
支持公开接口的 harness 应优先通过其正式导入导出接口适配；不声称所有 harness
都存在原生写回 API。Codex 原生批量写回尚无验证过的稳定插件接口，交接状态为
HANDOFF_PENDING，不能将文件生成成功当作原生接管成功。

安装、平台命令和精确版本见 [英文操作手册](README.md) 与 `release.json`。
Marketplace 展示名为 **Kang's plugins**，标识为 `cnkang`；安装选择器为
`qdrant-memory@cnkang`。
其中 `test_evidence` 路径相对于插件 ZIP 根目录（`VERIFICATION.md`）。
采用可移植 Agent Plugins 格式、Node 20+ stdio 启动层和已有 Python 3.11+ Runtime。
安装还需要 uv 和 PATH 中可用的 Git，以获取锁定提交的 Runtime 源码。
插件候选版本为 0.1.3，固定使用 MCP 0.3.1、Runtime 0.6.0、Skill 0.4.1 及 `release.json`
中的不可变源码提交；安装前确认准确依赖版本已公开。没有新增记忆引擎；
Hermes、DSH 和 WorkBuddy 按各自的版本及验收门禁独立发布。

每次更新插件后，重新执行下方固定的 `uv pip install` 命令，再重新连接。
启动器会核对已安装的 MCP distribution 版本是否与 `release.json` 一致；版本过期时会停止，
并且不会在启动时联网安装或升级依赖。

首次运行 setup 技能，选择新建隔离 Profile、预览后迁入原生记忆，或连接已授权的
现有目的地。默认 CPU FastEmbed 0.9.1；模型约 252 MB，下载需批准，已缓存可离线。
128 token 以上输入明确失败，不静默截断，也不切换云服务。Ollama 和兼容 OpenAI
的 embedding API 需显式选择，密钥只从环境读取。Codex 登录不等于 API Key。

先运行 `qdrant-memory --home PROFILE codex --codex-home APPROVED_HOME inspect` 和
`qdrant-memory --home PROFILE codex --codex-home APPROVED_HOME migrate --dry-run`，
审核原文件内容、跳过项目、目标 Scope 后，再运行
`qdrant-memory --home PROFILE codex --codex-home APPROVED_HOME migrate --confirm --verify`。
重试使用相同的 `--codex-home APPROVED_HOME`，并支持 `--resume --retry-failed`。
默认排除原始聊天、支持证据、代码块和疑似凭据。敏感信息检测不能替代人工审核。
原生文件不会移动、覆盖或删除。自定义 `QDRANT_MEMORY_CODEX_EXECUTABLE` 时，Python
默认取其虚拟环境中的解释器；若位置不同，也要设置 `QDRANT_MEMORY_CODEX_PYTHON`。
可执行文件必须是该解释器环境中的 `qdrant-memory` 入口；路径不匹配时 launcher 会拒绝启动。
多 Agent 并发必须使用原有 Shared Owner，不能让
多个独立 Ledger 直接写同一 Collection。受保护目的地不会被迁移 CLI 绕过。

退出时用 `qdrant-memory --home PROFILE codex export --output ./新目录 --confirm`，
再用 `qdrant-memory --home PROFILE codex verify --output ./新目录` 校验。
交接目录创建在 POSIX 使用目录描述符，在 Windows 使用经检查的原生句柄和私有
ACL；不支持的文件系统以及 Windows 网络路径、重解析路径会被拒绝。标准 Runtime
JSON 导出/导入仍可用于其他接入方。
审核交接文件，通过当前 Codex 支持的交互要求保存获准事实，启用原生记忆并在新
会话确认实际接管。涉及云端模型处理需先批准。AGENTS.md 属于项目指令，不是
原生记忆导入。保留 Qdrant 直至确认迁移结果；禁用/卸载不删除数据和备份。

模型或 embedding 切换需要新的 Collection 或 Profile。创建新目的地、
重新 embedding、恢复重试并验证，经批准后切换；原 Collection 保留，用于回退。

Codex Marketplace `cnkang` 从这个公开 GitHub 仓库分发插件。OpenAI 公共目录是
另一条独立提交渠道；这个本地 stdio 插件尚未提交到该目录。真实验收和未完成项见
仓库验证记录。
