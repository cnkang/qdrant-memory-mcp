# Universal Owner 开发状态（源码预览）

日期：2026-10-20。本页描述研发分支，不代表已经发布或可直接投入生产。
正式发布依赖保持 Runtime 0.4.0；MCP 源码版本仍为 0.2.2，GitHub Release
核验时是 Draft。新能力需要明确安装已审查的 Runtime 源码。

| 能力 | 当前边界与证据 |
|---|---|
| 本机单 Owner、多客户端 | 复用 Runtime、Ledger、CAS、回执和恢复；已有独立进程 MCP 测试 |
| Hermes Native Owner | 同一个 Provider、Runtime、宿主 LLM；明确规则才自动保存 project |
| HTTPS Streamable HTTP | 官方 Python SDK；loopback Gateway + 同机 TLS proxy；双容器真实 TLS 测试 |
| 同 Agent 跨设备 private | 独立 principal/device/token 映射到同一 logical agent；不迁移旧 private |
| Pi 自动记忆 | 官方 Pi 1.3.0 生命周期；真实 session + 确定性模型；Owner 负责提取与持久化 |
| Hermes → Pi 自动交接 | 真实 Hermes MemoryManager、同一 Owner、验证 TLS、Pi 独立进程新会话测试 |
| Codex、DSH、WorkBuddy、OpenCode | 继续 explicit MCP / assisted；不宣称自动生命周期已实现 |
| OAuth/OIDC、浏览器认证 | 未实现；当前只有受控的预配置独立服务凭据 |
| Embedded / Server / Cloud | 均保留；新代码本地验证 Embedded、Server TLS/JWT；新 Cloud 验收 SKIPPED |
| 真实模型质量 | 已有 qwen3:8b 小样本提取诊断 FAIL；不作为生产质量承诺 |

[Pi 配置与测试](../integrations/pi/README.md)区分 Hook 契约、真实 Pi session、
真实 Hermes → Pi HTTPS 链路。模型和 Embedding 使用 deterministic fixtures
的 Host 验收，不等同于真实模型质量、Host UI 手动验收或实际公网部署。

Pi outbox 只读当前获授权会话中本扩展自己的事件，使用不可变事件 ID 重试。
事件绑定 Owner URL 与凭据摘要；更换 Owner/凭据时不会把旧事件自动发到新空间。
旋转凭据后尚未发送的旧事件需管理员明确处理，不能自动重绑定。摘要不包含
可直接使用的明文 Token。共享召回通过每次请求的 ephemeral context Hook 注入，
拒绝、删除或撤权之后不复用旧召回，也不将共享召回持久化到会话历史。

`cross-harness.yml` 新增 Required 实际宿主交接 lane，固定 Runtime 源码和
Hermes Host SHA，不读取 Cloud Secret。Runtime 的 `shared-security.yml`
新增 SDK 1.x / 2.x 双容器 HTTPS lane。已有 Cloud protected workflow 保留。
Workflow 文件存在不代表已执行，具体 GitHub Run 状态以最终研发报告为准。

发布顺序：先审查并发布 Runtime 新版本，再有独立 PR 更新 MCP 的正式依赖与
Managed lockfile，最后更新 canonical Skill 支持版本。当前不更改正式版本号、
发布包、合并 PR、迁移用户数据或配置线上服务。
