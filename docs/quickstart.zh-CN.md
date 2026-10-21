# 最少步骤：用本地 Ollama 启用长期记忆

适用于 WorkBuddy，也适用于能启动 stdio MCP 的 Codex、OpenCode 等客户端。
使用本地 Ollama 和 Qdrant embedded，不需要 Docker、Qdrant Server、云账号或
Embedding API Key。当前版本仍需 Python/uv 和一次配置；连接器安装成功不代表
存储已经就绪。

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

创建一个新的私人目录，例如用户主目录下的 `.qdrant-memory-workbuddy`。
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

其他 agent 使用各自的新目录和 `agent_id`。在终端运行下列命令，把
`/path/to/workbuddy-profile` **全部替换**为刚才的绝对路径；含空格时保留引号。
Windows 也填写实际的绝对路径，JSON 中反斜杠写成 `\\`，或使用 `/`。

```sh
uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp --home "/path/to/workbuddy-profile" init
uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp --home "/path/to/workbuddy-profile" doctor
```

初始化会调用本地模型、创建本地 collection，并检查模型维度和存储兼容性。
两条命令都成功后再连接。平时和重启后无需重复初始化。若提示已有 collection、
模型不匹配或锁被占用，先解决原因，不要添加 reset 参数或删除数据/锁文件。

## 4. 在客户端连接 MCP

WorkBuddy 中添加自定义 stdio MCP，使用以下配置；将路径替换为步骤 3 的同一个目录。
受管连接器使用其数据根目录下的 `profiles/workbuddy/local`，不会自动选择这里的
自定义 profile。直接运行不带 `--home` 的 uvx 接口才默认使用 `~/.qdrant-memory`。
此设置只启用一个实例，避免同时启用受管连接器与自定义实例。

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.2.2", "qdrant-memory-mcp", "--home", "/path/to/workbuddy-profile", "mcp"],
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
