# Qdrant Memory MCP

共享生产部署请参阅[部署安全指南](docs/shared-deployment-security.md)。Owner 必须独占数据库应用写凭据，MCP 授权不能替代此要求。Runtime 0.5.0 已包含目的地保护和 shared doctor，须由操作者配置这些控制。支持边界请查看 [Owner 支持记录](docs/universal-owner-status.zh-CN.md)。

## One Memory, Multiple Agents — 可选启用的共享 owner

本分发新增显式启用的单 owner 共享服务和 stdio 桥接，需安装 Runtime 0.5.0。见[共享接入指南](integrations/shared/README.md)。私有默认配置与 DSH/WorkBuddy 托管配置不变；Hermes Native Provider 自动共享提取尚未实现。

这是 Qdrant Memory 的独立 PyPI 包装与 MCP Registry 分发仓库。
所有业务逻辑来自唯一的 [Python Runtime](https://github.com/cnkang/hermes-plugin-qdrant-memory)，
本仓库不复制 Runtime 或 [Agent Skill](https://github.com/cnkang/skills/tree/main/qdrant-memory)。
`qdrant-memory-mcp` 直接引用 `qdrant_memory.standalone:main`，固定依赖
`hermes-plugin-qdrant-memory[mcp]==0.5.0`，不需要安装 Hermes。

源码对齐、WorkBuddy 资产和兼容边界见 [0.2.4 发布说明](docs/releases/0.2.4.zh-CN.md)。

使用固定版本安装命令前，请在 [PyPI 版本页面](https://pypi.org/project/qdrant-memory-mcp/0.2.4/)
确认该版本已公开发布。

**版本：** 分发 0.2.4 固定依赖 Runtime 0.5.0，支持 MCP Python SDK 1.x 和 2.x
（`mcp>=1.30,<3`）；四个固定作用域工具和 stdio 启动参数保持一致。
保留不同但高度相似文本的显式写入修复，
无需 LLM。下文安装命令使用这些精确版本。发行产物见
[分发 PyPI 页面](https://pypi.org/project/qdrant-memory-mcp/) 和
[Runtime PyPI 页面](https://pypi.org/project/hermes-plugin-qdrant-memory/)。三个仓库的版本独立管理。
Skill 仅提供可选指导，不是运行依赖。Hermes 的自动提取和 prefetch 仍属于
原生集成；普通 MCP 仅执行明确请求的记忆操作，不自动提取每轮对话。

## 安装与配置

最少步骤见 [本地 Ollama 快速开始](docs/quickstart.zh-CN.md)，包括复用已有模型、
缺少模型时的安装指引、独立 WorkBuddy profile、连接配置和首次保存/搜索验证。
这条本地路径不需要 Qdrant Server、Docker、云账号或 Embedding API Key；
本直接路径仍需要准备 Python/uv，并完成一次 profile 配置。受管的 WorkBuddy
连接器和 DSH Bundle 则由 Node.js 准备这些依赖。

需要 Python 3.11+，以及 [uv](https://docs.astral.sh/uv/) 或 Python 虚拟环境。
必须自行配置存储和 Embedding 服务。
在可信 profile 目录内创建 `qdrant-memory.json`：

```json
{
  "schema_version": 1,
  "scope": {"user_id": "my-user", "agent_id": "my-agent"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "mode": "plugin", "provider": "ollama", "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434", "dimensions": 2560, "distance": "Cosine"
  }
}
```

示例要求自己启动 Ollama 并安装对应模型。将路径替换为自己的绝对路径：

```bash
uvx --from qdrant-memory-mcp==0.2.4 qdrant-memory-mcp --home /path/to/profile init
uvx --from qdrant-memory-mcp==0.2.4 qdrant-memory-mcp --home /path/to/profile mcp
```

省略 `--home` 时使用 `~/.qdrant-memory`，与 Hermes profile 独立。
Registry 默认运行 `uvx --from qdrant-memory-mcp==0.2.4 qdrant-memory-mcp mcp`，
应先配置、初始化默认目录。
客户端可通过 `mcp` 前面的可选 `--home` 参数选择自定义 profile。

也可以使用虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install qdrant-memory-mcp==0.2.4
.venv/bin/qdrant-memory-mcp --home /path/to/profile init
.venv/bin/qdrant-memory-mcp --home /path/to/profile mcp
```

Windows 使用 `.venv\Scripts\python.exe` 和 `.venv\Scripts\qdrant-memory-mcp.exe`。
Qdrant Embedded、Server、Cloud 和 OpenAI-compatible Embedding 的配置见
[原始配置文档](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/configuration.md)。
凭据由可信进程环境提供（如 `QDRANT_API_KEY`、`EMBEDDING_API_KEY`），不要提交密钥。
首次测试请使用独立的临时存储，现有 collection 的复用必须由操作者明确选择。

## 客户端示例

Codex `config.toml`：

```toml
[mcp_servers.qdrant_memory]
command = "uvx"
args = ["--from", "qdrant-memory-mcp==0.2.4", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"]
```

OpenCode `opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "qdrant_memory": {
      "type": "local",
      "command": ["uvx", "--from", "qdrant-memory-mcp==0.2.4", "qdrant-memory-mcp", "--home", "/path/to/profile", "mcp"],
      "enabled": true
    }
  }
}
```

Pi 需要另外安装 MCP 客户端扩展；将上述 command/args 填入该扩展支持的配置。
本仓库不声称 Pi 内置 MCP，也不声称通用扩展配置格式。
这些是配置示例；分发测试使用官方 Python MCP SDK，不把未实测的 Agent 应用列为已验证。
各客户端的实证范围与限制见 Runtime 的
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

## WorkBuddy 与 DeepSeek Harness

WorkBuddy 请使用[连接器说明](integrations/workbuddy/README.md)，DSH 请使用
[中文接入指南](docs/dsh-integration.zh-CN.md)。两者复用同一套 Runtime、四个 MCP
工具和权威 Skill，提供明确的记忆操作。已发布的[托管启动器](integrations/managed/README.md)
可通过 Node.js 准备私有 Python 环境、Runtime 与 CPU 模型，托管路线不需要系统
Python、uvx 或 Ollama。DSH Bundle 以 `@cnkang/qdrant-memory-dsh-bundle` 分发。
Hermes 原有 profile 和默认配置保持不变。详见[架构与版本矩阵](docs/cross-harness-architecture.md)
和[验证范围](docs/dsh-validation.md)。
