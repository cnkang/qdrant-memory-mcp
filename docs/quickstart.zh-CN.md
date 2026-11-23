# 稳定版 stdio MCP：本地 Ollama 快速开始

适用于 WorkBuddy，也适用于能启动 stdio MCP 的 Codex、OpenCode 等客户端。
使用本地 Ollama 和 Qdrant embedded，不需要 Docker、Qdrant Server、云账号或
Embedding API Key。此路径使用公开稳定包 `qdrant-memory-mcp==0.3.6`，固定依赖
Runtime 0.7.2；仍需 Python/uv 和一次 profile 配置。普通 MCP 只执行明确请求的记忆操作，
不会自动提取对话或预取记忆。连接器安装成功不代表存储已经就绪。

源码也在准备候选版 `qdrant-memory-mcp==0.3.7`，固定依赖已公开发布的 Runtime 0.7.3。
PyPI 和 MCP Registry 均发布前无法安装；此期间请继续使用本指南中的稳定版 0.3.6 命令。

## 1. 准备 Embedding 模型

已经安装 Ollama 和 `qwen3-embedding:4b`：打开 Ollama，直接进入下一步，
无需重复下载。可用 `ollama list` 查看已有模型。

没有 Ollama：从 [官方网站](https://ollama.com/download) 按操作系统安装。
macOS/Windows 打开应用；Linux 按官方安装说明启动服务。只有服务未运行时才执行
`ollama serve`，不要重复启动服务。然后在终端下载示例模型：

```sh
ollama pull qwen3-embedding:4b
```

这是一次模型下载，需要网络和磁盘空间；安装 MCP 不会替你安装 Ollama 或下载模型。
本地模型不需要 Ollama 云端登录或 API Key。

也可以使用已有的其他 **Embedding 模型**，但必须同时填写准确模型名和输出维度。
聊天模型不一定支持生成向量。下文配置仅对应 `qwen3-embedding:4b` 的 2560 维输出。
不要在已有存储上直接更换模型或维度；需要更换时创建新 profile，并采用明确的迁移流程。

## 2. 准备 MCP 启动环境

安装 [Python 3.11+](https://www.python.org/downloads/) 和
[uv](https://docs.astral.sh/uv/getting-started/installation/)，已有则跳过。
确认终端中能运行 `uvx --version`。WorkBuddy 等桌面客户端也必须能找到 `uvx`；
安装工具后重新打开客户端。首次启动会下载 Python 包，建议在终端先完成下一步，
避免客户端连接等待超时。无需安装 Hermes。

## 3. 创建独立 profile 并初始化一次

选择一个新的私人目录，例如用户主目录下的 `.qdrant-memory-workbuddy`。
先确认目录和其中的 `qdrant-memory.json` 都不存在；不要覆盖已有配置或 profile。
不要使用已有 Hermes 或其他 agent 的 profile。记下该目录的**绝对路径**。

在这个目录中新建 `qdrant-memory.json`，填写：

```json
{
  "schema_version": 1,
  "scope": {"user_id": "local-user", "agent_id": "workbuddy"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "mode": "plugin",
    "provider": "ollama",
    "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434",
    "dimensions": 2560,
    "distance": "Cosine"
  }
}
```

下方稳定版命令使用已公开发布的 `qdrant-memory-mcp==0.3.6`，固定依赖 Runtime 0.7.2。
安装前请在 [PyPI](https://pypi.org/project/qdrant-memory-mcp/0.3.6/) 确认版本。
MCP 0.3.7 候选版固定依赖 Runtime 0.7.3；请等 PyPI 和 MCP Registry 均发布 0.3.7 后再用候选命令。

其他 agent 使用各自的新目录和 `agent_id`。在终端运行下列命令，把
`/path/to/workbuddy-profile` **全部替换**为刚才的绝对路径；含空格时保留引号。
Windows 也填写实际的绝对路径，JSON 中反斜杠写成 `\\`，或使用 `/`。

```sh
uvx --from qdrant-memory-mcp==0.3.6 qdrant-memory-mcp --home "/path/to/workbuddy-profile" init
uvx --from qdrant-memory-mcp==0.3.6 qdrant-memory-mcp --home "/path/to/workbuddy-profile" doctor
```

MCP 0.3.7 在 PyPI 和 MCP Registry 均发布后，可使用以下精确版本命令：

```sh
uvx --from qdrant-memory-mcp==0.3.7 qdrant-memory-mcp --home "/path/to/workbuddy-profile" init
uvx --from qdrant-memory-mcp==0.3.7 qdrant-memory-mcp --home "/path/to/workbuddy-profile" doctor
```

初始化会调用本地模型、创建本地 collection，并检查模型维度和存储兼容性。
两条命令都成功后再连接。平时和重启后无需重复初始化。如遇到已有文件、已有 collection、
模型不匹配或兼容性错误、锁被占用，应先调查原因。
`WriterBusyError` 表示另一个 MCP 进程仍持有该 profile；先彻底停止该进程，再启动替代进程。
终端步骤也会预热固定版本的包，客户端可直接启动已缓存的命令。MCP 连接本身不会安装
Ollama、下载模型、初始化已有 collection 或迁移数据。不要覆盖配置、重建 profile、使用
`--force`、添加 reset 参数或删除数据/锁文件。若部分失败，先对同一 profile 运行 `doctor`
并检查结果，再决定下一步。

## 4. 在客户端连接 MCP

### VS Code Copilot

先完成步骤 1–3：启动 Embedding 服务，创建新 profile，再运行 `init` 和 `doctor`。
在工作区根目录创建 `.mcp.json`，使用 VS Code 原生 Copilot `mcpServers` 格式；
在聊天会话中选择 Copilot harness。`.vscode/mcp.json` 属于已弃用的 Local harness，
不是 Copilot 原生配置。

下方首个配置对应 MCP 0.3.7 候选版，固定依赖 Runtime 0.7.3。PyPI 和 MCP Registry
均发布 0.3.7 后才可使用；发布前请使用紧随其后的稳定版 0.3.6 配置。

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.3.7", "qdrant-memory-mcp", "--home", "/path/to/copilot-profile", "mcp"]
    }
  }
}
```

在 PyPI 和 MCP Registry 均发布 0.3.7 前，请使用以下公开稳定版 0.3.6 配置：

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.3.6", "qdrant-memory-mcp", "--home", "/path/to/copilot-profile", "mcp"]
    }
  }
}
```

Manifest 中可选的 `--home` 必须位于位置参数 `mcp` 之前。如果 VS Code 进程找不到
`uvx`，把 `command` 改成它的绝对路径。这条路径只提供显式的记忆搜索、新增、更新和删除；
不会自动提取对话，也不需要安装 Hermes 或 Agent Skill。

发布前可以用 `uv build --wheel` 构建候选 wheel，再用 `uv venv` 创建并激活独立虚拟环境，
运行 `uv pip install /path/to/qdrant_memory_mcp-0.3.7-py3-none-any.whl` 安装。
将 `command` 指向安装后的
`qdrant-memory-mcp` 可执行文件的绝对路径，`args` 设为
`["--home", "/path/to/copilot-profile", "mcp"]`。使用一次性测试 profile，
或在旧 MCP 进程停下后复制现有测试 profile。

在 Copilot 工具列表确认存在 `qdrant_memory_search`、`qdrant_memory_add`、
`qdrant_memory_update` 和 `qdrant_memory_delete`。让 Copilot 使用
`qdrant_memory_add` 保存一条带唯一标记的合成测试记忆，并确认真实工具调用和返回值。
停止并重启 MCP 服务，打开新的 Copilot 会话，不要粘贴原文，再要求它使用
`qdrant_memory_search` 找回该标记。

Embedded profile 同一时间只允许一个 writer lease。修改 `.mcp.json` 时，Copilot
可能为多个已打开的会话启动服务。第二个使用同一 profile 的进程会在初始化时收到
`WriterBusyError`。测试重启召回前，先停止上一会话的 MCP 进程并确认它已退出，
再打开新 Copilot 会话，让它启动新的 MCP 进程。

| 验证项 | 状态 |
|---|---|
| VS Code Copilot 桌面版，0.3.6 候选包 | PASS — macOS arm64，VS Code 1.146.0，Copilot harness，工作区 `.mcp.json`，本地 wheel，PyPI Runtime 0.7.2，MCP SDK 2.3.0。旧版记录召回、新增、搜索、重启召回、更新和删除均通过。 |
| VS Code Copilot 桌面版，PyPI 0.3.5 | PASS — VS Code 1.146.0，Runtime 0.7.1。发现四个工具，重启后在新会话成功召回。 |
| VS Code Copilot 桌面版，PyPI 0.3.6 | 已发布。上一条宿主结果使用候选 wheel；未记录用公开包复测的结果。 |
| CI 配置与 stdio 协议 | 0.3.6 候选包通过。[Distribution CI](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/44231566353) |
| Copilot CLI | PASS — GitHub Copilot CLI 1.0.112 已发现四个工具，并通过 stdio 对公开发布的 `qdrant-memory-mcp==0.3.5` 实际调用新增和搜索；重启 MCP 进程后，新 CLI 进程和会话召回了同一条合成记录 |
| GitHub Registry 一键安装 | NOT VERIFIED；手动配置不等于目录安装 |

2026-11-17，PyPI 0.3.5 安装保存并召回了合成标记
`VSCOPILOT-20261117-IK3Y7SOJ`，ID 为 `20251dcf-3e15-5586-919d-838412bc392f`。
2026-11-18，从 `76177dd` 构建的 0.3.6 wheel 在复制的 0.3.5 测试 profile 中找回
同一 ID。候选包新增 `VSCOPILOT-036-20261118-N8Q4HX`，返回 ID
`0abce594-6ce3-526a-8a0b-ac8ffe0849ac`。停止 MCP 进程前，以及新 Copilot 会话
启动新进程后，搜索均返回该 ID。更新后的文本也能读回，ID 保持一致。删除后，
再次搜索该标记，结果中没有该标记或 ID。

MCP Registry 元数据将 `0.3.5` 标记为 active/latest；这不能证明 GitHub 目录一键安装已通过。

### WorkBuddy 与其他 stdio MCP 客户端

WorkBuddy 中添加自定义 stdio MCP，使用以下配置；将路径替换为步骤 3 的同一个目录。
受管连接器使用其数据根目录下的 `profiles/workbuddy/local`，不会自动选择这里的
自定义 profile。直接运行不带 `--home` 的 uvx 接口才默认使用 `~/.qdrant-memory`。
此设置只启用一个实例，避免同时启用受管连接器与自定义实例。

下方配置使用公开稳定版 MCP 0.3.6。如果前面使用了 0.3.7 候选命令，请在 PyPI 和
MCP Registry 均发布 0.3.7 后，再把下面 `--from` 后的版本改为 0.3.7。

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.3.6", "qdrant-memory-mcp", "--home", "/path/to/workbuddy-profile", "mcp"],
      "timeout": 30000
    }
  }
}
```

如果桌面客户端找不到 `uvx`，将 `command` 改为它的绝对路径。
Codex、OpenCode、Pi 扩展的配置格式见 [客户端示例](../README.zh-CN.md#客户端示例)，
使用同样的命令和参数即可；Pi 需要单独安装支持 MCP 的扩展。

## 5. 保存并验证第一条记忆

连接后应发现四个 `qdrant_memory_*` 工具。依次对客户端说：

1. “请使用记忆工具记住：这是我的测试偏好，我喜欢简洁的中文回复。”
2. “请搜索刚才保存的回复语言偏好。”
3. 完全退出并重开客户端，再执行同一次搜索。

确认搜索工具确实返回记录，不能只看模型口头回答。需要修改或删除时先搜索，
让客户端使用搜索结果的准确 ID。不要保存密码、API Key 等秘密。

MCP 只执行显式搜索、保存、更新和删除，不会自动提取全部聊天内容。
本地路径中的记忆和查询发送到本机 Ollama，向量与记忆保存在本机 Qdrant/ledger；
召回内容也会返回客户端，并可能交给它使用的聊天模型。

## 遇到问题时

| 现象 | 下一步 |
| --- | --- |
| 找不到 `ollama` | 安装 Ollama，重开终端；已安装则检查其命令路径 |
| 连接本地模型失败 | 打开 Ollama，确认服务地址为 `http://127.0.0.1:11434`；自定义地址需同步修改新 profile |
| 模型不存在 | 用 `ollama list` 核对名称；仅在缺失时运行上面的 `ollama pull` |
| 模型不能生成向量/维度不匹配 | 核对它是 Embedding 模型；新 profile 使用正确维度，已有 collection 不自动重建 |
| 找不到 `uvx` | 安装 uv，重开桌面客户端，或在配置中指定 uvx 的绝对路径 |
| 连接超时 | 先在终端完成包下载、`init` 和 `doctor`，确认 Ollama 可用后重连 |
| profile/collection 未初始化 | 核对配置与命令中的 `--home` 路径完全一致，再对该新 profile 执行初始化 |
| 写入锁被占用 | 关闭正在使用同一 profile/存储的另一个 MCP、CLI 或 Hermes 进程后重试 |

当前错误信息经过脱敏，未必包含上述操作指引；可按本表排查。
不要公开包含个人路径、记忆内容或凭证的配置和日志。
服务细节见 [Ollama 快速入门](https://docs.ollama.com/quickstart) 与
[Embedding API](https://docs.ollama.com/api/embed)。
