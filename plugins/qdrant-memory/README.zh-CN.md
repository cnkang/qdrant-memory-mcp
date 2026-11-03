# Qdrant Memory for Codex

**One Memory. Multiple Agents. No Lock-in. 一份记忆，多个 Agent，自由迁移。**

使用现有 Qdrant Runtime，提供显式搜索、新增、更新、删除，以及 Codex v1/v2
语义记忆只读导入、可验证的 JSON/Markdown 导出。退出后无需插件即可读取数据。
支持公开接口的 harness 应优先通过其正式导入导出接口适配；不声称所有 harness
都存在原生写回 API。Codex 原生批量写回尚无验证过的稳定插件接口，交接状态为
HANDOFF_PENDING，不能将文件生成成功当作原生接管成功。

安装、平台命令和精确版本见 [英文操作手册](README.md) 与 `release.json`。
采用可移植 Agent Plugins 格式、Node 20+ stdio 启动层和已有 Python 3.11+ Runtime。
插件独立版本为 0.1.0。没有新增记忆引擎，也不修改 Hermes/DSH/WorkBuddy 集成。

首次运行 setup 技能，选择新建隔离 Profile、预览后迁入原生记忆，或连接已授权的
现有目的地。默认 CPU FastEmbed 0.9.1；模型约 252 MB，下载需批准，已缓存可离线。
128 token 以上输入明确失败，不静默截断，也不切换云服务。Ollama 和兼容 OpenAI
的 embedding API 需显式选择，密钥只从环境读取。Codex 登录不等于 API Key。

先运行 `codex inspect` 和 `codex migrate --dry-run`，审核原文件内容、跳过项目、
目标 Scope 后才以 `--confirm --verify` 导入。支持 `--resume --retry-failed`。
默认排除原始聊天、支持证据、代码块和疑似凭据。敏感信息检测不能替代人工审核。
原生文件不会移动、覆盖或删除。多 Agent 并发必须使用原有 Shared Owner，不能让
多个独立 Ledger 直接写同一 Collection。受保护目的地不会被迁移 CLI 绕过。

退出时用 `codex export --output ./新目录 --confirm`，再用 `codex verify` 校验。
审核交接文件，通过当前 Codex 支持的交互要求保存获准事实，启用原生记忆并在新
会话确认实际接管。涉及云端模型处理需先批准。AGENTS.md 属于项目指令，不是
原生记忆导入。保留 Qdrant 直至确认迁移结果；禁用/卸载不删除数据和备份。

升级或 embedding 切换必须保留原 Collection identity。模型不兼容时创建新目的地、
重新 embedding、恢复重试并验证，经批准后切换，旧数据用于回退。

当前是 GitHub Marketplace 候选包。真实验证和未完成项目见仓库验证记录。
OpenAI 公共目录的本地 MCP 需合作伙伴许可、完整依赖打包和真实 Desktop 验证，
未获官方审核通过，也未推送任何发布 tag 或向公共 Registry 发布。
