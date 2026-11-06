# DSH 原生 Qdrant Memory 生命周期适配器

这是一个仅运行于 DSH Host 的 Cordis 插件源码预览，为 DeepSeek Harness 提供可选的自动召回、记忆注入和完整轮次捕获。它通过已认证的 HTTPS Owner endpoint 使用现有 Python Runtime，不直接连接 Qdrant，不创建第二套 ledger，也不更改四个公开 MCP 工具。

插件针对 DSH `0.2.2-rc.1` 和 Node.js `24.9.0`。当前已发布的 Python Runtime 尚不接受这里使用的版本化候选事件。配套 Runtime 发布前，本源码包仅用于集成审查和本地验证；已发布的 MCP Bundle 和 Cordis overlay 仍是受支持路径。

## 安装

只有在兼容 Runtime Owner 已准备完成后，才把本地包安装到一个 DSH profile：

```sh
dsh plugin --profile <profile> add /absolute/path/to/integrations/dsh/native
```

三个功能开关默认均为 `false`。先配置 Owner 服务和捕获策略，再通过官方 DSH Plugin Manager 按 profile 启用：

```yaml
auto_recall:
  enabled: false
auto_capture:
  enabled: false
memory_injection:
  enabled: false
```

召回需要同时启用 `auto_recall.enabled` 和 `memory_injection.enabled`；捕获可独立启用。只在明确批准的 profile 中设置为 `true`。

## Owner 连接与权限

启动现有 Runtime Owner，并启用 lifecycle endpoint 和带有捕获规则的显式写入 grant。在启动 DSH 的可信进程环境中设置以下变量：

| 变量 | 值 |
| --- | --- |
| `QDRANT_MEMORY_RUNTIME_PYTHON` | 安装了兼容 Runtime 的 Python 解释器绝对路径 |
| `QDRANT_MEMORY_DSH_OWNER_URL` | 以 `/mcp` 结尾的 Owner HTTPS endpoint |
| `QDRANT_MEMORY_DSH_OWNER_TOKEN` | 已配置的 Owner grant token；不要写入 profile YAML |
| `QDRANT_MEMORY_RUNTIME_CA_FILE` | 可选的私有 CA bundle 绝对路径 |

适配器只把 Owner token 和必要的进程路径传给 Python 子进程，不继承其他 DSH 凭证，不打印请求内容，也不会在授权失败后改用另一个身份。Owner 从 grant 推导 scope。TLS 和 Owner 部署请遵循[共享部署安全指南](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/shared-deployment-security.md)。不要让无关 profile 共用一个 token。

## 配置示例

三个开关的默认值和随包 patch 都为关闭；以下 YAML 不包含凭证。

**全部关闭：**

```yaml
auto_recall:
  enabled: false
auto_capture:
  enabled: false
memory_injection:
  enabled: false
```

**仅自动召回：**

```yaml
auto_recall:
  enabled: true
memory_injection:
  enabled: true
auto_capture:
  enabled: false
```

**仅自动捕获：**

```yaml
auto_recall:
  enabled: false
memory_injection:
  enabled: false
auto_capture:
  enabled: true
```

**自动捕获和召回：**

```yaml
auto_recall:
  enabled: true
memory_injection:
  enabled: true
auto_capture:
  enabled: true
```

嵌入模型和存储只能配置在 Python Owner profile 中，不属于 DSH profile。请先创建新的 Owner destination，并阅读 [Runtime 嵌入设置](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/local-embedding.md)与[共享 Owner 部署](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/README.zh-CN.md)。候选事件契约尚未在已发布 Runtime 中提供，因此以下命令只展示 Owner 配置方式，暂不能和已发布 Runtime 一起启用原生适配器。

为新的本地 CPU Owner 显式安装 Runtime 的 `local` extra，并创建独立 profile：

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote,local]==0.6.0'
qdrant-memory setup --profile /absolute/private/dsh-owner --embedding-provider fastembed --agent-id dsh-owner
```

使用已安装的 Ollama 模型时，无需 Runtime 的 `local` extra：

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote]==0.6.0'
qdrant-memory setup --profile /absolute/private/dsh-owner --embedding-provider ollama --model qwen3-embedding:4b --dimensions 2560 --agent-id dsh-owner
```

若使用异地 HTTPS Owner，请按[HTTPS Owner 指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/remote-owner.md)配置受保护的 destination、TLS proxy 和独立 grant。每个 DSH profile 使用单独的 token：

```text
QDRANT_MEMORY_DSH_OWNER_URL=https://memory.example.com/mcp
QDRANT_MEMORY_DSH_OWNER_TOKEN=<由密钥管理器提供的 profile 专属凭证>
QDRANT_MEMORY_RUNTIME_PYTHON=/absolute/path/to/compatible-runtime/bin/python
```

不要把 Owner 的 Qdrant 或 embedding 凭证交给 DSH。Owner grant 决定可读写 scope；不同身份的 DSH、Hermes 和 WorkBuddy 私有记忆不会自动合并。

## 生命周期与恢复限制

- 召回在 `agent/pre-step` 看到新的直接用户消息时执行一次。它通过 Owner 调用现有 `qdrant_memory_search`，再向当前 step 添加标记为 `qdrant-memory` 的日志用户消息。文本会 JSON 转义并标明为不可信历史数据。
- 捕获只处理已完成轮次。适配器使用记录的 provider/model route 通过 DSH LLM facade 输出严格候选 JSON，再把版本化候选交给 Python Owner。涉及替换时会提供一段精确的用户文本摘录（最多 2 KiB）；助手全文不会发送给 Runtime。Runtime 执行授权、scope、关系审查、去重、ledger 恢复和 Qdrant 写入。
- 工具输出、非用户注入消息、被中断的助手输出及未完成的 turn 不会进入捕获。凭证样式的 transcript 或候选会被跳过。
- 捕获前会等待 DSH session flush，再读取经过校验的 session log。重启恢复最多检查最近八个已完成轮次的 Owner receipt。重试复用原事件 ID 和候选内容；失败或待处理 receipt 交给 Owner 恢复处理，不会在同一 ID 下重新抽取。
- 队列有界。成功的 DSH flush 和 Owner receipt 才构成可恢复边界；在此之前崩溃可能留下未捕获轮次，不能承诺零丢失。

## 迁移、回退和故障排查

已发布的 Bundle 和 Python/uvx overlay 继续提供显式 MCP 操作。等候兼容 Runtime 后，可在保留现有 profile 和数据的前提下，在同一 profile 中加装原生插件。每个 profile 最多保留一个已发布 MCP 路径（Bundle 或 overlay），可与原生插件并存。不要同时启用 Bundle 和 overlay。

回退时先关闭三个开关，移除原生插件，再重启 DSH profile：

```sh
dsh plugin --profile <profile> remove @cnkang/qdrant-memory-dsh-native
```

回退不会删除 profile 文件、Owner receipt、Ledger 记录、Qdrant 记忆或 embedding cache。不要为了卸载插件清空这些数据。捕获结果不确定时，先按事件 ID 查询 Owner receipt；单纯的传输错误不能证明事件未接受。

召回缺失时检查两个召回开关、grant 的搜索权限、endpoint 证书和 token。捕获缺失时检查 `auto_capture.enabled`、Runtime 候选事件版本、写入 grant 和捕获规则。Owner 不可用时，普通 DSH 对话继续运行；不要在同一不确定事件 ID 下重复排队写入。

## 验证状态

在本机运行 `npm ci` 和 `npm test`。单元测试使用合成 session/Owner，不代表真实 DSH AgentLoop、真实模型、Owner 联网或 GUI 验收。完整证据、CI 状态和未覆盖场景见[验证报告](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-native/validation.zh-CN.md)。
