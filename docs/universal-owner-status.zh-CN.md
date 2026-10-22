# Universal Owner 功能与限制（源码预览）

[English](universal-owner-status.md)

本页说明源码预览的功能和支持边界。
正式发行版使用 Runtime 0.4.0。
预览功能需要单独安装支持相应接口的已审查 Runtime 源码。
源码预览不代表生产环境验收。

## 功能

| 功能 | 支持边界 |
|---|---|
| 一个 Owner、多个客户端 | 客户端共用一个 Runtime、Ledger、版本比较与交换（CAS）、回执和恢复机制。独立进程 MCP 测试验证这些边界。 |
| Hermes Native Owner | Hermes 使用同一个 Provider、Runtime 和宿主模型。只有明确批准的规则才能将记录自动保存到 project 空间。 |
| HTTPS Streamable HTTP | 网关使用官方 Python SDK，并监听环回地址。该配置使用同机 TLS 代理。双容器测试验证 TLS 和网络隔离。 |
| 同一 Agent 跨设备的 private 记忆 | 独立的 principal、device 和 token 映射到同一个 logical agent。已有 private 记录不会自动迁移。 |
| Pi 自动记忆 | 适配器使用官方 Pi 1.3.0 生命周期钩子。Owner 负责提取和持久化。测试使用真实 Pi 会话和确定性模型。 |
| Hermes-to-Pi 自动交接 | 测试使用真实 Hermes MemoryManager 回调、同一个 Owner、经过验证的 HTTPS 和独立 Pi 进程中的新会话。 |
| Codex、DSH、WorkBuddy、OpenCode | 这些宿主支持显式 MCP 或辅助使用方式。自动记忆需要各自独立、经过验证的生命周期适配器。 |
| OAuth、OIDC、浏览器认证 | 源码预览不支持这些认证方式。各客户端使用预先配置的独立服务凭据。 |
| Embedded、Server、Cloud | 三种部署方式均保留。验证范围包括 Embedded 和使用 TLS/JWT 的 Server。独立的 Runtime Cloud Owner 测试已通过，并已删除测试集合。集合级凭据限制尚未验证。 |
| 模型质量 | Runtime CI 使用固定模型进行功能冒烟测试。冒烟通过不代表提取质量达标。部署前必须使用目标模型运行完整质量测试。 |

## Pi 会话与授权

Pi 仅重放当前获授权会话中本扩展保存的待处理事件。
重试使用相同的事件 ID。
事件绑定 Owner URL 和捕获凭据的摘要。
更换 Owner 或凭据不会将旧事件自动发送到新空间。
凭据轮换后，管理员必须明确处理尚未发送的旧事件。
摘要不包含可直接使用的明文 token。

适配器通过每次模型请求的临时 `context` 钩子获取共享召回。
它将召回标记为不可信数据，并保留来源、空间和版本信息。
请求失败、拒绝访问、删除记录或撤销权限后，它不会复用旧召回。
它不会将共享召回保存到会话历史。
捕获凭据和只读召回凭据可以使用独立 scope，并分别撤销。
Owner 控制身份、权限和空间选择。

## 验证与部署边界

[Pi 配置与测试](../integrations/pi/README.md)说明钩子测试、真实 Pi 会话测试和 Hermes-to-Pi HTTPS 测试。
这些测试使用确定性的模型和 Embedding 测试数据。
它们不验证生产模型质量、宿主用户界面或公网部署。
不同宿主需要独立的验收证据。

[Runtime Cloud Owner 测试](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/39691871575)
已在 main 上通过 1 项端到端测试，没有跳过的测试。
本次使用 Runtime [24f9b1110ee99237f432afefbc7af7573bfae494](https://github.com/cnkang/hermes-plugin-qdrant-memory/tree/24f9b1110ee99237f432afefbc7af7573bfae494)，与固定的预览版本一致。
测试删除了记录和集合，独立清理检查确认删除完成。
测试使用测试专用 API Key，因此不代表集合级凭据隔离验收通过。
[Runtime 模型指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/model-quality.md)
区分功能冒烟结果和完整模型质量结果。
这些 Runtime 结果不代表生产环境验收或宿主 UI 验收通过。

## 手动桌面验收（2026-10-22）

独立的手动测试使用 WorkBuddy 5.8.3 和 DeepSeek Harness 0.2.1-rc.2。
两个应用通过 `shared-mcp` 连接同一个隔离的环回 Owner。
每个应用使用独立凭据。测试仅使用合成记录、Embedded Qdrant，
以及本机已有的 `qwen3-embedding:4b` 模型，维度为 2560。
实测 Runtime 版本为 [7994e54de83fa8d39e566724dd88dd13b34970ee](https://github.com/cnkang/hermes-plugin-qdrant-memory/tree/7994e54de83fa8d39e566724dd88dd13b34970ee)。
该版本的 Runtime 包文件与上文固定的预览版本一致。

| 手动检查 | 结果 |
|---|---|
| WorkBuddy 添加与检索 | PASS。工具返回一条记录及其版本。 |
| DSH 独立会话召回 | PASS。ID、版本和创建者一致。 |
| DSH CAS 更新及相同请求重放 | PASS。重放返回相同的新版本，仍只有一条记录。 |
| WorkBuddy 使用旧版本更新 | PASS。`SharedConflictError` 拒绝写入，DSH 更新内容保留。 |
| Owner 停止及重启 | PASS。DSH 读回相同的 ID、新版本、内容及更新者。 |
| 清理 | PASS。DSH 只删除测试记录；两个应用随后均返回零条记录，存储检查确认零个 point。 |

测试恢复了 WorkBuddy 原有自定义 MCP 配置，停用了临时 DSH bundle，
停止 Owner，并删除临时凭据及 policy。
空的本地测试 profile 和合成操作 Ledger 保留用于审计。
本次测试不代表跨设备 HTTPS UI、应用重启、原生 bundle 安装或自动记忆生命周期验收通过。
它独立于上文的确定性 CI 测试。

正式发行版仅在兼容性验证完成后采用新的 Runtime 版本。
源码预览不会自动迁移用户数据或更改线上服务。
[共享服务配置](../integrations/shared/README.md)说明独立凭据和 HTTPS 示例。
部署前应阅读[部署安全说明](shared-deployment-security.md)。
