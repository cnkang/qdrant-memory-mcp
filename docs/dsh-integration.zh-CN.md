# 在 DeepSeek Harness 中使用 Qdrant 长期记忆

共享部署的 DSH 只应持有独立的 Owner 客户端令牌，数据库写凭据由 Owner 独占。见[部署安全指南](shared-deployment-security.md)。普通托管 Bundle 保持私有模式，不会自动登记共享目的地。

通过 DSH 官方 MCP 客户端，可以搜索、保存、更新和删除长期记忆。
记忆在新的会话和服务重启后仍然保留。它提供明确的记忆操作，不会自动保存每一轮对话。

[English](dsh-integration.md) · [验证范围](dsh-validation.md)

## 安装 Bundle（托管 CPU）

纯配置 Bundle 通过官方 `@deepseek-ai/dsh-mcp-client` 连接已发布的托管启动器。
需要 Node.js（DSH 本身依赖），不需要系统 Python、uvx、Ollama 或 Qdrant Server。
先准备共享后端：

```sh
npx -y @cnkang/qdrant-memory-launcher@0.1.0-rc.8 prepare dsh
```

等待输出 `{"ready":true,"host":"dsh"}`。准备过程会下载私有 Python 环境、固定版本的
Runtime wheel 和经过校验的 CPU 嵌入模型，可能需要数分钟并需要网络。然后把 Bundle
安装到一个 profile：

```sh
dsh plugin --profile <name> add @cnkang/qdrant-memory-dsh-bundle
```

若所用 npm 镜像尚未同步该包，可改从仓库 Release 下载
`cnkang-qdrant-memory-dsh-bundle-0.1.6.tgz`，用文件路径安装。不启动即可先验证层：

```sh
dsh --profile <name> --dump-config
```

DSH 会先运行临时探测进程，再启动常驻连接。探测进程不会执行安装或下载模型；
准备始终是上面的显式步骤。后端就绪前，工具会明确提示没有执行任何操作，
写入不会被排队。DSH 的数据目录（`<managed-root>/profiles/dsh/local`）与 WorkBuddy、
Hermes 相互独立。更新、卸载与恢复说明见 [Bundle 说明](../integrations/dsh/bundle/README.md)。

## 原生生命周期适配器（未发布预览）

仓库还包含可选的[原生 Cordis 适配器](../integrations/dsh/native/README.md)。
它使用 DSH 模型和会话生命周期，在明确启用后执行召回、注入和完整轮次候选提取，
再把候选交给现有 Python Owner。三个开关默认都为 `false`。召回需要同时启用
`auto_recall.enabled` 和 `memory_injection.enabled`。

该适配器针对 `@deepseek-ai/dsh@0.2.2-rc.1`。配套 Runtime 改动已在 0.6.1 合并，但尚未发布到 PyPI，因此它暂时不能与已发布 Runtime 一起作为受支持的安装路径。
在 Runtime 0.6.1 发布前，请使用上面的 Bundle 或 Python/uvx overlay。
原生包尚未发布，也没有真实模型或 GUI 验收结论。详见
[原生设计与支持状态](dsh-native/design.md)。配置、回退和验证边界见
[英文设置指南](../integrations/dsh/native/README.md)、
[中文设置说明](../integrations/dsh/native/README.zh-CN.md)和
[验证报告](dsh-native/validation.zh-CN.md)。

## 备选：Python/uvx overlay

直接运行下列固定版本命令。`qdrant-memory-mcp` 0.3.1 已发布到 PyPI，此路径不需要源码 checkout。

需要 Python 3.11+、uv/uvx 和可用的嵌入服务（例如 Ollama）。按照
[快速入门](quickstart.zh-CN.md) 配置，但把 profile 改为独立的
`~/.qdrant-memory-dsh`，在其中创建 `qdrant-memory.json`，设置身份、模型和服务地址。
然后执行：

在运行初始化前，请在 `QDRANT_MEMORY_DSH_PROFILE` 选定的目录中创建并配置
`qdrant-memory.json`（scope、嵌入模型和服务地址）。全新的目录不会继承
`~/.qdrant-memory-dsh` 的设置；`init`、`doctor` 和 MCP server 都使用该选定目录。
若 `QDRANT_MEMORY_DSH_PROFILE` 使用字面量路径，请写成绝对路径，例如
`"$HOME/memory"`；`~/memory` 在带引号变量中不会展开。示例用 `$HOME` 展开默认值，确保
shell 文件操作和 Runtime 使用同一目录。

复用已有 patch 前，请确认其 `--home` 指向当前选择的 profile；如果硬编码了其他路径，请先更新再启动。

启动检查通过 uv 获取固定版本的 PyYAML，仅解析节点而不执行 `!!js`。
仅接受只包含 insert 操作的 overlay，以及 `config.args` 中的
`--from PACKAGE` 或 `--from=PACKAGE` 前缀。其他 patch 操作可能覆盖已验证的参数，
因此会阻止启动。
检查还会拒绝重复的 MCP serverName 和不匹配的 `--home`；请保留发布的动态
home 表达式，或者使用已准备 profile 的字面路径。
启动前还会检查 `dsh web --dump-config` 返回的当前 profile 配置。若已包含
`qdrant-memory` server，或与 overlay 存在服务名冲突，则阻止启动；请先移除
已有 memory 连接。检查只解析 YAML 节点、不执行标签，随后删除临时文件。
配置导出失败或内容无效时同样不会启动。

```sh
PROFILE="${QDRANT_MEMORY_DSH_PROFILE:-$HOME/.qdrant-memory-dsh}"
export QDRANT_MEMORY_DSH_PROFILE="$PROFILE"
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home "$PROFILE" init &&
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home "$PROFILE" doctor &&
(
  mkdir -p "$PROFILE"
  PATCH="$PROFILE/qdrant-memory.cordis.yml"
  if [ ! -e "$PATCH" ]; then
    TMP="$(mktemp "${PATCH}.XXXXXX")"
    # Bash 可能在失败分支执行前退出（例如 Ctrl-C），因此任何退出路径都要
    # 保证残留的半下载文件不留在 profile 目录里。
    trap 'rm -f "$TMP"' EXIT INT
    if curl -fsSL -o "$TMP" \
      https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.1/integrations/dsh/qdrant-memory.cordis.yml; then
      mv "$TMP" "$PATCH"
      trap - EXIT INT
    else
      rm -f "$TMP"
      echo "Patch download failed; DSH was not launched." >&2
      exit 1  # This setup block is a subshell, safe when sourced too.
    fi
  fi
  # 仅解析 YAML 节点，不执行 !!js 表达式。
  COMPOSED="$(mktemp)"
  if dsh web --dump-config > "$COMPOSED"; then
    if uv run --no-project --with PyYAML==6.0.3 python -I - "$PATCH" qdrant-memory-mcp==0.3.1 "$PROFILE" "$COMPOSED" <<'PY'
import sys
import yaml
from pathlib import Path
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


def mapping(node):
    """Read a mapping without constructing or evaluating tagged values."""
    assert isinstance(node, MappingNode)
    result = {}
    for key, value in node.value:
        assert isinstance(key, ScalarNode) and key.tag == 'tag:yaml.org,2002:str'
        assert key.value not in result, 'Duplicate YAML key'
        result[key.value] = value
    return result


def profile_servers(node, ancestors=()):
    """Inspect composed YAML nodes without evaluating tags or following cycles."""
    assert id(node) not in ancestors, 'Cyclic profile YAML'
    if isinstance(node, MappingNode):
        item = mapping(node)
        assert not (item.get('id') and item['id'].value == 'cnkang-qdrant-memory-mcp'), 'Memory plugin already installed'
        name = item.get('name')
        group = item.get('group')
        is_group = group is not None and group.value == 'true'
        # Plugin groups store their child entries under config. Inspect those
        # entries even when the group itself has no profile id.
        if not item.get('id') and not is_group and not (
            name and name.value == '@deepseek-ai/dsh-mcp-client'
        ):
            return
        if name and name.value == '@deepseek-ai/dsh-mcp-client':
            assert name.tag == 'tag:yaml.org,2002:str'
            server = mapping(item['config'])['serverName']
            assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
            yield server.value
        children = [item['config']] if is_group and isinstance(item.get('config'), SequenceNode) else [
            value for _, value in node.value
        ]
    elif isinstance(node, SequenceNode):
        children = node.value
    else:
        return
    for child in children:
        yield from profile_servers(child, (*ancestors, id(node)))


try:
    with open(sys.argv[1], encoding='utf-8') as source:
        root = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(root, SequenceNode)
    plugins = []
    servers = []
    for operation in root.value:
        entries = mapping(operation)['insert']
        assert isinstance(entries, SequenceNode)
        for entry in entries.value:
            plugin = mapping(entry)
            name = plugin.get('name')
            if name is not None:
                assert isinstance(name, ScalarNode) and name.tag == 'tag:yaml.org,2002:str'
            if name and name.value == '@deepseek-ai/dsh-mcp-client':
                server = mapping(plugin['config'])['serverName']
                assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
                servers.append(server.value)
            if plugin.get('id') and plugin['id'].value == 'cnkang-qdrant-memory-mcp':
                plugins.append(plugin)
    assert len(plugins) == 1, 'Expected exactly one memory plugin'
    name = plugins[0]['name']
    assert name.tag == 'tag:yaml.org,2002:str' and name.value == '@deepseek-ai/dsh-mcp-client'
    config = mapping(plugins[0]['config'])
    with open(sys.argv[4], encoding='utf-8-sig') as source:
        composed = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(composed, SequenceNode), 'Invalid composed profile'
    existing = list(profile_servers(composed))
    assert 'qdrant-memory' not in existing, 'Memory server already installed'
    assert len(servers + existing) == len(set(servers + existing)), 'Conflicting MCP serverName'
    command = config['command']
    assert command.tag == 'tag:yaml.org,2002:str' and command.value == 'uvx'
    args = config['args']
    assert isinstance(args, SequenceNode)
    # Tagged values stay as YAML nodes and are never evaluated.
    prefix = []
    for arg in args.value[:3]:
        assert isinstance(arg, ScalarNode) and arg.tag == 'tag:yaml.org,2002:str'
        prefix.append(arg.value)
    package = sys.argv[2]
    assert (prefix == ['--from', package, 'qdrant-memory-mcp']
            or prefix[:2] == ['--from=' + package, 'qdrant-memory-mcp'])
    tail = args.value[3 if prefix[0] == '--from' else 2:]
    assert len(tail) in (2, 3) and tail[-1].value == 'mcp'
    assert tail[-1].tag == 'tag:yaml.org,2002:str'
    if len(tail) == 3:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value == '--home'
        home = tail[1]
    else:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value.startswith('--home=')
        home = ScalarNode('tag:yaml.org,2002:str', tail[0].value[len('--home='):])
    assert isinstance(home, ScalarNode)
    if home.tag == 'tag:yaml.org,2002:js':
        trusted = (
            "process.env.QDRANT_MEMORY_DSH_PROFILE || "
            "require('node:path').join(require('node:os').homedir(), '.qdrant-memory-dsh')"
        )
        assert ' '.join(home.value.split()) == trusted, 'Unverified dynamic home'
    else:
        assert home.tag == 'tag:yaml.org,2002:str'
        assert Path(home.value).expanduser().resolve() == Path(sys.argv[3]).expanduser().resolve(), 'Profile mismatch'
except (AssertionError, KeyError, AttributeError, OSError, yaml.YAMLError):
    sys.exit('Invalid patch: require one unambiguous memory server, qdrant-memory-mcp==0.3.1 and the prepared profile; DSH was not launched.')
PY
    then
      rm -f "$COMPOSED"
      dsh web --patch "$PATCH"
    else
      rm -f "$COMPOSED"
      false
    fi
  else
    rm -f "$COMPOSED"
    echo "Profile config dump failed; DSH was not launched." >&2
    false
  fi
)
```

Windows PowerShell 5.1 请使用对应命令：

```powershell
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  throw "uvx is required; DSH was not launched."
}
$MemoryProfile = if ($env:QDRANT_MEMORY_DSH_PROFILE) { $env:QDRANT_MEMORY_DSH_PROFILE } else { Join-Path $HOME ".qdrant-memory-dsh" }
$env:QDRANT_MEMORY_DSH_PROFILE = $MemoryProfile
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home $MemoryProfile init
if ($LASTEXITCODE -ne 0) { throw "Runtime init failed; DSH was not launched." }
uvx --from qdrant-memory-mcp==0.3.1 qdrant-memory-mcp --home $MemoryProfile doctor
if ($LASTEXITCODE -ne 0) { throw "Runtime doctor failed; DSH was not launched." }
$PatchDir = $MemoryProfile
$Patch = Join-Path $PatchDir "qdrant-memory.cordis.yml"
New-Item -ItemType Directory -Force -Path $PatchDir | Out-Null
if (-not (Test-Path $Patch)) {
  $Draft = "$Patch.download"
  try {
    Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/cnkang/qdrant-memory-mcp/v0.3.1/integrations/dsh/qdrant-memory.cordis.yml" -OutFile $Draft -ErrorAction Stop
    Move-Item -Force $Draft $Patch
  } catch {
    # 默认错误偏好下 Write-Error 不会中断脚本；改为 throw，避免继续执行
    # 配置导出并产生误导性的校验失败。
    throw "Patch download failed; DSH was not launched."
  } finally {
    Remove-Item -Force $Draft -ErrorAction SilentlyContinue
  }
}
# Parse YAML nodes only: !!js expressions are never evaluated.
$ValidatePatch = @'
import sys
import yaml
from pathlib import Path
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


def mapping(node):
    """Read a mapping without constructing or evaluating tagged values."""
    assert isinstance(node, MappingNode)
    result = {}
    for key, value in node.value:
        assert isinstance(key, ScalarNode) and key.tag == 'tag:yaml.org,2002:str'
        assert key.value not in result, 'Duplicate YAML key'
        result[key.value] = value
    return result


def profile_servers(node, ancestors=()):
    """Inspect composed YAML nodes without evaluating tags or following cycles."""
    assert id(node) not in ancestors, 'Cyclic profile YAML'
    if isinstance(node, MappingNode):
        item = mapping(node)
        assert not (item.get('id') and item['id'].value == 'cnkang-qdrant-memory-mcp'), 'Memory plugin already installed'
        name = item.get('name')
        group = item.get('group')
        is_group = group is not None and group.value == 'true'
        # Plugin groups store their child entries under config. Inspect those
        # entries even when the group itself has no profile id.
        if not item.get('id') and not is_group and not (
            name and name.value == '@deepseek-ai/dsh-mcp-client'
        ):
            return
        if name and name.value == '@deepseek-ai/dsh-mcp-client':
            assert name.tag == 'tag:yaml.org,2002:str'
            server = mapping(item['config'])['serverName']
            assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
            yield server.value
        children = [item['config']] if is_group and isinstance(item.get('config'), SequenceNode) else [
            value for _, value in node.value
        ]
    elif isinstance(node, SequenceNode):
        children = node.value
    else:
        return
    for child in children:
        yield from profile_servers(child, (*ancestors, id(node)))


try:
    with open(sys.argv[1], encoding='utf-8') as source:
        root = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(root, SequenceNode)
    plugins = []
    servers = []
    for operation in root.value:
        entries = mapping(operation)['insert']
        assert isinstance(entries, SequenceNode)
        for entry in entries.value:
            plugin = mapping(entry)
            name = plugin.get('name')
            if name is not None:
                assert isinstance(name, ScalarNode) and name.tag == 'tag:yaml.org,2002:str'
            if name and name.value == '@deepseek-ai/dsh-mcp-client':
                server = mapping(plugin['config'])['serverName']
                assert isinstance(server, ScalarNode) and server.tag == 'tag:yaml.org,2002:str'
                servers.append(server.value)
            if plugin.get('id') and plugin['id'].value == 'cnkang-qdrant-memory-mcp':
                plugins.append(plugin)
    assert len(plugins) == 1, 'Expected exactly one memory plugin'
    name = plugins[0]['name']
    assert name.tag == 'tag:yaml.org,2002:str' and name.value == '@deepseek-ai/dsh-mcp-client'
    config = mapping(plugins[0]['config'])
    with open(sys.argv[4], encoding='utf-8-sig') as source:
        composed = yaml.compose(source, Loader=yaml.BaseLoader)
    assert isinstance(composed, SequenceNode), 'Invalid composed profile'
    existing = list(profile_servers(composed))
    assert 'qdrant-memory' not in existing, 'Memory server already installed'
    assert len(servers + existing) == len(set(servers + existing)), 'Conflicting MCP serverName'
    command = config['command']
    assert command.tag == 'tag:yaml.org,2002:str' and command.value == 'uvx'
    args = config['args']
    assert isinstance(args, SequenceNode)
    # Tagged values stay as YAML nodes and are never evaluated.
    prefix = []
    for arg in args.value[:3]:
        assert isinstance(arg, ScalarNode) and arg.tag == 'tag:yaml.org,2002:str'
        prefix.append(arg.value)
    package = sys.argv[2]
    assert (prefix == ['--from', package, 'qdrant-memory-mcp']
            or prefix[:2] == ['--from=' + package, 'qdrant-memory-mcp'])
    tail = args.value[3 if prefix[0] == '--from' else 2:]
    assert len(tail) in (2, 3) and tail[-1].value == 'mcp'
    assert tail[-1].tag == 'tag:yaml.org,2002:str'
    if len(tail) == 3:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value == '--home'
        home = tail[1]
    else:
        assert tail[0].tag == 'tag:yaml.org,2002:str' and tail[0].value.startswith('--home=')
        home = ScalarNode('tag:yaml.org,2002:str', tail[0].value[len('--home='):])
    assert isinstance(home, ScalarNode)
    if home.tag == 'tag:yaml.org,2002:js':
        trusted = (
            "process.env.QDRANT_MEMORY_DSH_PROFILE || "
            "require('node:path').join(require('node:os').homedir(), '.qdrant-memory-dsh')"
        )
        assert ' '.join(home.value.split()) == trusted, 'Unverified dynamic home'
    else:
        assert home.tag == 'tag:yaml.org,2002:str'
        assert Path(home.value).expanduser().resolve() == Path(sys.argv[3]).expanduser().resolve(), 'Profile mismatch'
except (AssertionError, KeyError, AttributeError, OSError, yaml.YAMLError):
    sys.exit('Invalid patch: require one unambiguous memory server, qdrant-memory-mcp==0.3.1 and the prepared profile; DSH was not launched.')
'@
$Composed = [IO.Path]::GetTempFileName()
try {
  $ConsoleEncoding = [Console]::OutputEncoding
  try {
    # PowerShell decodes native stdout using Console.OutputEncoding.
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $Dump = @(dsh web --dump-config)
  } finally {
    [Console]::OutputEncoding = $ConsoleEncoding
  }
  if ($LASTEXITCODE -ne 0) { throw "Profile config dump failed; DSH was not launched." }
  [IO.File]::WriteAllText($Composed, ($Dump -join "`n"))
  $ValidatePatch | uv run --no-project --with PyYAML==6.0.3 python -I - $Patch qdrant-memory-mcp==0.3.1 $MemoryProfile $Composed
  if ($LASTEXITCODE -ne 0) { throw "Patch/profile validation failed; DSH was not launched." }
} finally {
  Remove-Item -Force $Composed -ErrorAction SilentlyContinue
}
dsh web --patch $Patch
```

overlay patch 已包含在发布的 `v0.3.1` tag 中，可直接下载，不需要源码 checkout。
请把文件放在包环境之外，并在每次启动 DSH 时把其本地路径传给 `--patch`。

Windows 请使用对应的绝对路径。启动 DSH 前可用环境变量
`QDRANT_MEMORY_DSH_PROFILE` 指定其他独立 profile。不要选择正在使用的
Hermes 或 WorkBuddy 数据目录。启用 overlay 前先完成依赖准备；DSH 不会替第三方
MCP 服务安装软件、选择模型或初始化数据库。

overlay 只为本次启动添加一个独立插件，不覆盖 `cordis.patch.yml`，不修改默认
Profile。需要长期启用时，可保留 `--patch` 参数，或把单个 `insert` 条目合并到
选定 profile 的现有 patch 中。不要直接覆盖原文件，也不要在同一 profile 同时启用
Bundle 和 Python overlay。其他 profile 不受影响。

默认工具名是 `mcp__qdrant-memory__qdrant_memory_search`，以及同前缀的
`add`、`update`、`delete`。改动 `serverName` 后请以实际发现的工具名为准。
原始工具参数和 scope 限制保持不变；继续使用 DSH 自身的工具授权机制。

## 安装共用 Skill

唯一权威来源是 [cnkang/skills 的 qdrant-memory](https://github.com/cnkang/skills/tree/main/qdrant-memory)。
把整个目录及其 references 安装到项目的 `.agents/skills/qdrant-memory`，或者用
DSH 的 `customSkillDirs` 指向包含该目录的已审核 checkout。支持符号链接的系统
可以链接到权威 checkout。DSH 会识别 `qdrant-memory/SKILL.md`，无需维护另一套
DSH 专用 Skill。若多个目录已有同名 Skill，请选定一个版本，避免重复来源。

## 凭证、重试与数据保护

DSH 会清理继承环境中名称包含 KEY、PASSWORD、SECRET、TOKEN 的变量以及
`DSH_*` 变量。Python overlay 已通过 `!!js process.env` 显式转发
`QDRANT_API_KEY` 和 `EMBEDDING_API_KEY`。请用可信 shell 或凭证管理器设置值，
不要把真实凭证写进 YAML、命令参数、Skill、对话或日志。若 profile 使用其他
凭证变量，需显式增加对应转发。仅无须认证的服务可以使用空值。托管 CPU 预设无需密钥。

工具提示准备中或准备失败时，表示没有成功执行操作。先修复安装问题，再重试；
不要用无限重连掩盖安装失败。已派发的写操作中断后，重试前先核对具体操作及其 ID；不确定的写操作，除非重复本身安全，否则不要重复。
数据目录被占用时，正常关闭原连接；不要删锁、重置数据库或修改 fingerprint 强行启动。

先移除 Bundle 或本次 overlay，再停止或重启该 profile：运行中的 profile
保留已加载的 Bundle 集合，重启后才会关闭活动 MCP 连接并释放存储写租约。
磁盘数据会保留。
验收时在会话 A 保存合成事实，在不传入旧对话的会话 B 检索并使用；再按返回的 ID
更新和删除，并完整重启 DSH 验证持久化。自动化官方客户端测试与真实模型/GUI
会话验收分别记录，不相互替代。

适配器遵循官方
[MCP 客户端契约](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)、
[记忆指南](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/mcp-memory.md)
和 [Skill 文件系统 provider](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md)。
