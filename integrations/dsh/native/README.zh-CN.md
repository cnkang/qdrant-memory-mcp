# DSH 原生 Qdrant Memory 生命周期适配器

这是一个仅运行于 DSH Host 的 Cordis 插件源码预览，为 DeepSeek Harness 提供可选的自动召回、记忆注入和完整轮次捕获。它通过已认证的 HTTPS Owner endpoint 使用现有 Python Runtime，不直接连接 Qdrant，不创建第二套 ledger，也不更改四个公开 MCP 工具。

插件针对 DSH `0.2.2-rc.1`、Node.js `24.9.0` 或更高版本，以及 Python Runtime 0.6.1 或更高版本。Runtime 0.6.1 提供此适配器使用的版本化候选事件和持久 receipt 重试。本 DSH 插件仍以私有源码 bundle 分发；MCP Bundle 和 Cordis overlay 是独立的公开支持路径。

## 安装

安装兼容 Runtime 后，再通过官方 Plugin Manager 将本地包安装到一个 DSH profile：

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
| `QDRANT_MEMORY_DSH_OWNER_URL` | 路径必须恰为 `/mcp` 的 Owner HTTPS endpoint |
| `QDRANT_MEMORY_DSH_OWNER_TOKEN` | 已配置的 Owner grant token；不要写入 profile YAML |
| `QDRANT_MEMORY_RUNTIME_CA_FILE` | 可选的私有 CA bundle 绝对路径 |

适配器只把 Owner token 和必要的进程路径传给 Python 子进程，不继承其他 DSH 凭证，不打印请求内容，也不会在授权失败后改用另一个身份。子进程以 `-I -S` 加固定 site-packages 引导从解释器所在目录启动，项目内容与 site 启动文件都无法遮蔽已安装的 Runtime。Owner 从 grant 推导 scope。TLS 和 Owner 部署请遵循[共享部署安全指南](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/shared-deployment-security.md)。不要让无关 profile 共用一个 token。

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

嵌入模型和存储只能配置在 Python Owner profile 中，不属于 DSH profile。请先创建新的 Owner destination，并阅读 [Runtime 嵌入设置](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/local-embedding.md)与[共享 Owner 部署](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/README.zh-CN.md)。Runtime 0.6.1 提供原生适配器使用的候选事件与重试契约，但已并入、尚未上 PyPI（公开最新为 0.6.0）。发布前请使用下方源码 pin；后文两条 `==0.6.1` 命令在 PyPI 发布 Runtime 0.6.1 前都会失败，请勿提前使用。

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote,local] @ git+https://github.com/cnkang/hermes-plugin-qdrant-memory.git@6df73703419f061e77b9b640c15ddf6609d26e58'
```

为新的本地 CPU Owner 显式安装 Runtime 的 `local` extra，并创建独立 profile：

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote,local]==0.6.1'
qdrant-memory setup --profile /absolute/private/dsh-owner --embedding-provider fastembed --agent-id dsh-owner
```

使用已安装的 Ollama 模型时，无需 Runtime 的 `local` extra：

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote]==0.6.1'
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
- 捕获只处理已完成轮次。适配器使用记录的 provider/model route 将用户和助手轮次文本提交给 DSH LLM facade，以生成严格候选 JSON，再把版本化候选交给 Python Owner。Owner event 没有独立的 assistant 字段，但候选可能包含从助手文本提取的事实，并会发送给 Runtime。涉及替换时还会提供一段精确的用户文本摘录（最多 2 KiB）。Runtime 执行授权、scope、关系审查、去重、ledger 恢复和 Qdrant 写入。
- 工具输出、非用户注入消息、被中断的助手输出及未完成的 turn 不会进入捕获。凭证样式的 transcript 或候选会被跳过。
- 捕获前会等待 DSH session flush，再读取经过校验的 session log。重启恢复会按每批八个 turn 检查保存激活边界之后的所有完成 turn 的 Owner receipt，并跳过由持久 recovery-progress 记录标记为已解决的轮次；失败的捕获会持续重试。对于 `ACCEPTED` receipt，适配器只按事件 ID 请求重试，由 Runtime 复用原先保存的不可变候选计划。候选内容不会进入 DSH session log，也不会在同一 ID 下重新提取；其他待处理或失败的 receipt 由 Owner 恢复。
- 队列有界。成功的 DSH flush 和 Owner receipt 才构成可恢复边界；在此之前崩溃可能留下未捕获轮次，不能承诺零丢失。

## 迁移、回退和故障排查

已发布的 Bundle 和 Python/uvx overlay 继续提供显式 MCP 操作。等候兼容 Runtime 后，可在保留现有 profile 和数据的前提下，在同一 profile 中加装原生插件。每个 profile 最多保留一个已发布 MCP 路径（Bundle 或 overlay），可与原生插件并存。不要同时启用 Bundle 和 overlay。

回退时先关闭三个开关，移除原生插件，再重启 DSH profile：

```sh
dsh plugin --profile <profile> remove @cnkang/qdrant-memory-dsh-native
```

回退不会删除 profile 文件、Owner receipt、Ledger 记录、Qdrant 记忆或 embedding cache。不要为了卸载插件清空这些数据。捕获结果不确定时，先按事件 ID 查询 Owner receipt；单纯的传输错误不能证明事件未接受。

召回缺失时检查两个召回开关、grant 的搜索权限、endpoint 证书和 token。捕获缺失时检查 `auto_capture.enabled`、Runtime 候选事件版本、写入 grant 和捕获规则。Owner 不可用时，普通 DSH 对话继续运行；不要在同一不确定事件 ID 下重复排队写入。

适配器以 `-I -S` 启动 Runtime，并通过引导脚本把解释器自身的 `site-packages` 加入导入路径，但不处理 `.pth` 或 `sitecustomize`；因此 `QDRANT_MEMORY_RUNTIME_PYTHON` 必须指向 `site-packages` 已安装 Runtime 的解释器：专用 venv、`uv tool` 环境，或启用 `--system-site-packages` 且基础解释器已安装 Runtime 的 venv；`--user` 与 `PYTHONPATH` 安装对该子进程不可见。

`-I` 隔离工作树、`PYTHONPATH` 和用户 site-packages；`-S` 跳过 site 初始化，项目控制的启动代码与 `.pth` 文件无法在 `QDRANT_MEMORY_DSH_OWNER_TOKEN` 存在时执行。引导脚本遵循 venv 的 `include-system-site-packages` 设置。解释器二进制及其已安装包仍须是可信安装；不要使用位于 DSH 项目内的虚拟环境。

## 诊断指标

插件在进程内维护召回请求/命中/失败/缓存命中、注入记忆数量与字符数、捕获 turn 的 seen/eligible/committed、捕获失败、backlog 丢弃、恢复次数与累计召回延迟等计数器。`apply()` 返回的 disposer 通过 `metrics()` 暴露快照，供程序化宿主与测试使用；DSH 没有读取它的原生状态命令。计数器不包含对话文本或凭证。Runtime receipt 只返回状态，因此无法提供 mutation 类型拆分和 dedupe rate。

## 验证状态

在本机运行 `npm ci` 和 `npm test`。单元测试使用合成 session/Owner，不代表真实 DSH AgentLoop、真实模型、Owner 联网或 GUI 验收。完整证据、CI 状态和未覆盖场景见[验证报告](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-native/validation.zh-CN.md)。
