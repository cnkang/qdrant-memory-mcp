# Qdrant Memory MCP

**One Memory. Multiple Agents. No Lock-in.**

Codex 与其他非 Hermes Agent 的默认入口是公开稳定的 stdio MCP。
从[快速开始](docs/quickstart.zh-CN.md)开始：`qdrant-memory-mcp==0.3.6`
固定依赖 Runtime 0.7.2，并提供四个显式记忆工具。Hermes 用户请使用
[Hermes 原生 Plugin Catalog 安装指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/INSTALL.md)。

源码正在准备 MCP 0.3.7 候选版，固定依赖已发布的 Runtime 0.7.3。在 PyPI
和 MCP Registry 均显示 0.3.7 已发布前，请继续使用公开稳定版 0.3.6。
发布后客户端应使用精确参数前缀
`["--from", "qdrant-memory-mcp==0.3.7", "qdrant-memory-mcp"]`。

面向 AI Agent 的持久化、可移植、权限感知记忆，以 MCP 适配层分发 Qdrant Memory Runtime。

共享生产部署请参阅[部署安全指南](docs/shared-deployment-security.md)。Owner 必须独占数据库应用写凭据，MCP 授权不能替代此要求。部署前须配置目的地保护和 shared doctor。支持边界请查看 [Owner 支持记录](docs/universal-owner-status.zh-CN.md)。

## One Memory, Multiple Agents — 可选启用的共享 owner

本分发新增显式启用的单 owner 共享服务和 stdio 桥接，需安装 Runtime 0.7.2。见[共享接入指南](integrations/shared/README.md)。私有默认配置与 DSH/WorkBuddy 托管配置不变；Hermes Native Provider 自动共享提取尚未实现。

下一个 MCP 候选版本为 `qdrant-memory-mcp==0.3.7`，固定依赖已公开发布的 Runtime 0.7.3。
确认 PyPI 和 MCP Registry 均已发布后再使用；此前请继续使用上方公开稳定版 0.3.6。

## 已发布路径与验收范围

| 路径 | 已发布产物与固定依赖 | 当前状态与验收边界 |
|---|---|---|
| [稳定 stdio MCP](docs/quickstart.zh-CN.md) | PyPI `qdrant-memory-mcp==0.3.6`，Runtime 0.7.2 | 公开稳定版；协议 CI 使用隔离 profile 和确定性 embedding fixture，不代表所有真实模型/Provider 组合均已验收 |
| [Codex 插件](plugins/qdrant-memory/README.zh-CN.md) | 候选版 0.1.4；MCP 0.3.5、Runtime 0.7.1（`cc5cac025f5d18afb5c698b2b5db444e30fc240e`）、Skill 0.4.6（`2cb0b4d61ba2aae9a04c9eaf571f804918e151ce`） | 尚未提交公共插件目录；有官方 Codex CLI 检查，Desktop GUI 与原生记忆接管另行验证 |
| [DSH Bundle](docs/dsh-integration.zh-CN.md) | npm 公开预发布 `@cnkang/qdrant-memory-dsh-bundle@0.2.0-rc.5`；DSH 0.2.2-rc.1、launcher 0.1.0-rc.14、Runtime 0.7.2 | 可安装的预发布版；真实模型/Cloud 与 Desktop GUI 验收仍未完成 |
| [WorkBuddy connector](integrations/workbuddy/README.md) | GitHub release `workbuddy-v0.2.6`；launcher 0.1.0-rc.10、Runtime 0.6.2、Skill 0.4.4 | 精确 tag 打包与协议门禁通过；Marketplace GUI 导入、干净机器配置和完整重启仍未验证 |

宿主适配包各自独立版本。候选版或可从 npm 安装不等于真实模型、Cloud、Desktop 或市场验收完成；选择前请读各自宿主指南和证据。

这是 Qdrant Memory 的独立 PyPI 包装与 MCP Registry 分发仓库。
所有业务逻辑来自唯一的 [Python Runtime](https://github.com/cnkang/hermes-plugin-qdrant-memory)，
本仓库不复制 Runtime 或 [Agent Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory)。
`qdrant-memory-mcp` 直接引用 `qdrant_memory.standalone:main`，固定依赖
`hermes-plugin-qdrant-memory[mcp]==0.7.2`，不需要安装 Hermes。

Runtime 固定版本和升级指导见 [0.3.6 发布说明](docs/releases/0.3.6.zh-CN.md)。

使用固定版本安装命令前，请在 [PyPI 版本页面](https://pypi.org/project/qdrant-memory-mcp/0.3.6/)
确认该版本已公开发布。
[已发布的 0.3.5 指南](https://github.com/cnkang/qdrant-memory-mcp/blob/v0.3.5/README.zh-CN.md)仍可用于上一版。
源码候选版不代表对应的 PyPI 或 npm 版本已经可用。

**版本：** 分发 0.3.6 固定依赖 Runtime 0.7.2，支持 MCP Python SDK 1.x 和 2.x
（`mcp>=1.30,<3`）；四个固定作用域工具和 stdio 启动参数保持一致。
下文安装命令使用这些精确版本。发行产物见
[分发 PyPI 页面](https://pypi.org/project/qdrant-memory-mcp/) 和
[Runtime PyPI 页面](https://pypi.org/project/hermes-plugin-qdrant-memory/)。三个仓库的版本独立管理。
发布顺序见[发布清单](docs/publishing.zh-CN.md)。
Skill 仅提供可选指导，不是运行依赖。Hermes 的自动提取和 prefetch 仍属于
原生集成；普通 MCP 仅执行明确请求的记忆操作，不自动提取每轮对话。

## 宿主支持矩阵

验证级别：仅配置示例、协议级测试、官方 SDK/CLI 测试、真实宿主测试、真实桌面 GUI 测试、未验证。

| 宿主 | 原生 Provider | 显式 MCP 工具 | 自动捕获 | 自动召回 | 共享 Owner | 远程访问 | 验证 |
|---|---|---|---|---|---|---|---|
| Hermes | 是 | 是（通过 standalone） | 是 | 是 | 可选 | 是 | 真实宿主测试 |
| OpenCode | 否 | 是 | 否 | 否 | 通过 Owner | 是 | 真实宿主测试（双设备） |
| Pi | 否 | 是（扩展） | 可选适配器 | 可选适配器 | 通过 Owner | 是 | 真实宿主测试 |
| DeepSeek Harness | 否（生命周期适配器） | 是（DSH bundle） | 可选预览 | 可选预览 | 通过 Owner | 是 | Bundle 0.2.0-rc.5；真实模型/Cloud/Desktop 验收未完成 |
| WorkBuddy | 否 | 是（connector） | 否 | 否 | 通过 Owner | 是 | Connector 0.2.6 打包/协议通过；GUI Marketplace、干净机器和重启未验证 |
| Codex | 否 | 是 | 否 | 否 | 通过 Owner | 是 | 候选版 0.1.4；官方 CLI 已测，尚未提交公共目录 |
| VS Code Copilot | 否 | 是（四个 MCP 工具） | 否 | 否 | 通过 Owner | 是 | [CI 配置/协议 PASS](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/44061227907)；Copilot CLI 1.0.112 PASS；VS Code 1.146.0 Copilot 桌面新增/重启召回 PASS；GitHub Registry 一键安装 NOT VERIFIED |

本分发不对任何 MCP 宿主自动提取对话。自动捕获与召回需要原生 Provider 或生命周期适配器。DSH 自动功能为可选启用；npm 预发布包可安装，但真实模型/Cloud 与 Desktop GUI 验收仍待完成。
已测试的 CLI、源码修订和模型提供方见 [Codex 验证记录](docs/codex-plugin-verification.md)；
桌面 GUI 与原生记忆接管需要分别验证。

## 稳定 stdio 安装

请按[固定版本快速开始](docs/quickstart.zh-CN.md)逐步检查环境、建立独立 profile、
运行 `init` 和 `doctor`、复用本地模型、配置宿主并验证工具写入/检索/重连。
先在终端准备包与 profile，再连接客户端；连接时不自动安装、下载模型、初始化已有
collection 或迁移数据。Hermes profile 请使用
[Runtime 原生安装指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/INSTALL.md)。

## 客户端示例

Codex `config.toml`：

```toml
[mcp_servers.qdrant_memory]
command = "uvx"
args = ["--from", "qdrant-memory-mcp==0.3.6", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"]
```

OpenCode `opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "qdrant_memory": {
      "type": "local",
      "command": ["uvx", "--from", "qdrant-memory-mcp==0.3.6", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"],
      "enabled": true
    }
  }
}
```

Pi 需要另外安装 MCP 客户端扩展；将上述 command/args 填入该扩展支持的配置。
本仓库不声称 Pi 内置 MCP，也不声称通用扩展配置格式。
这些是配置示例；协议验收使用官方 Python MCP SDK。各宿主证据单独记录于
[架构与支持边界](docs/cross-harness-architecture.md)与 Runtime 的
[客户端证据与限制](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/mcp.md)。

## 工具、安全与限制

| 工具 | 输入 | 用途 |
|---|---|---|
| `qdrant_memory_search` | `query`，可选 `category` | 作用域内检索，返回 ID、分数、来源 |
| `qdrant_memory_add` | `text` | 持久化显式记忆 |
| `qdrant_memory_update` | 精确 `id`、替换 `text` | 经过授权检查后更新 |
| `qdrant_memory_delete` | 精确 `id` | 经过授权检查后删除 |

profile 固定 user/agent scope；模型参数、客户端身份不能覆盖它，知道 ID 不等于获得权限。
迁移、导出、重置、批量删除仍是可信操作者 CLI 命令，见
[维护文档](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/standalone.md)。

MCP 使用本地 **stdio**，不提供公网 HTTP/SSE 服务、远程认证、resources 或 prompts。
stdout 只承载协议，错误经过脱敏。不支持无协调的多进程写入；一个 MCP 进程会
持有 profile/destination 的 writer lease。不同 profile 或机器不共享分布式锁。

数据流为客户端 → Runtime → Embedding → Qdrant 与本地 SQLite Ledger。
本地模型与本地 Qdrant 可实现本地数据处理；云 Embedding 会接收记忆/查询文本，
云 Qdrant 会接收向量和 payload，客户端或模型也会接收召回文本。
操作者需要管理保留策略、权限与 profile 文件。

## 概念与证据

- 共享 vs 可移植 vs 备份：[Runtime 可移植性指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/portability.md)
- 跨 Harness 架构：[docs/cross-harness-architecture.md](docs/cross-harness-architecture.md)
- Shared Owner 状态：[docs/universal-owner-status.zh-CN.md](docs/universal-owner-status.zh-CN.md)
- 验证限制：[docs/dsh-validation.md](docs/dsh-validation.md)

验证报告仅适用于其中记录的版本、工作负载与宿主环境。
短时协议或云端运行不能证明新版本已经通过 24 小时验收。

## 验证与开发

CI 对 Linux/macOS/Windows、Python 3.11/3.14 的 wheel/sdist 安装运行真实协议测试，
覆盖初始化、工具发现、四项操作、重启持久化与恢复、scope 拒绝、错误脱敏、stdout。
使用临时目录、Embedded Qdrant、确定性本地 HTTP Embedding fixture，
不访问私人 Qdrant、Hermes profile 或个人记忆。云服务兼容性参见 Runtime 的验证证据。

CI 优先使用正式 PyPI Runtime。新 Runtime 发布前，CI 使用 `runtime-source.json` 固定的不可变修订
构建本地 wheel；正式包元数据始终依赖固定 PyPI 版本，发布流程禁止这种回退。
详见 [CI 与依赖维护](docs/ci.md)、[发布清单](docs/publishing.md)、
[架构](docs/architecture.md) 与
[Runtime 验证](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/validation.md)，
以及可选的 [Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory)。

## 依赖边界

运行依赖仅为 `hermes-plugin-qdrant-memory[mcp]`。sdist 包含 Python 验收测试，
但不包含需要外部 Runtime checkout、DSH 客户端资源或未随 sdist 分发的 Node fixture
的测试；部分宿主锁文件与仅 Node 使用的 `.mjs` 测试也不包含在内。
wheel 仅含分发元数据。开发依赖声明在 `[project.optional-dependencies].dev`，
不会为最终用户安装。

## WorkBuddy 与 DeepSeek Harness

WorkBuddy 请使用[连接器说明](integrations/workbuddy/README.md)，DSH 请使用
[中文接入指南](docs/dsh-integration.zh-CN.md)。两者复用同一套 Runtime、四个 MCP
工具和权威 Skill，提供明确的记忆操作。已发布的[托管启动器](integrations/managed/README.md)
可通过 Node.js 准备私有 Python 环境、Runtime 与 CPU 模型，托管路线不需要系统
Python、uvx 或 Ollama。DSH Bundle 以 `@cnkang/qdrant-memory-dsh-bundle` 分发。
Hermes 原有 profile 和默认配置保持不变。详见[架构与版本矩阵](docs/cross-harness-architecture.md)
和[验证范围](docs/dsh-validation.md)。
