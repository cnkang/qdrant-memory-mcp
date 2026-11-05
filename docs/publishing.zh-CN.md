# 0.3.1 发布清单

[English](publishing.md) | [简体中文](publishing.zh-CN.md)

在操作员明确确认 Runtime/PyPI/Registry 发布之前，不执行任何发布 tag 或 workflow
dispatch。

构建前在 release PR 中准备版本化的包及 Registry 元数据、README 示例和发布说明。
`verify_metadata.py` 要求 README 的安装固定版本与发行包版本一致，且 PyPI 文件不可变。
示例仅标识目标发行版本，不能证明该版本已公开可用。使用安装命令前，须核实准确的公开
版本。只有下列检查确认两个公开端点后，才可宣布发布已可用。

1. 核验已公开的 Runtime 0.6.0 发行版及准确依赖。不要为本次分发重新创建其 tag，
   也不要再次发布。
2. 复核已有的 PyPI Trusted Publisher（PyPI 账号步骤）：
   - `hermes-plugin-qdrant-memory`：owner `cnkang`，仓库
     `hermes-plugin-qdrant-memory`，workflow `publish.yml`，环境 `pypi`。
   - `qdrant-memory-mcp`：owner `cnkang`，仓库 `qdrant-memory-mcp`，
     workflow `publish.yml`，环境 `pypi`。
3. 在提示时批准受保护的 GitHub 环境。版本 tag 必须指向 main 分支的提交，并与包元数据
   一致。发行不能覆盖已有版本。复用已验证的公开 Runtime 0.6.0 文件。
4. 在公开依赖模式下运行分发验收：在新环境中仅使用准确的公开 Runtime PyPI 发行版
   构建并测试 wheel 和 sdist。
5. 确认后创建分发 tag v0.3.1。其 workflow 先构建和测试，再执行受保护的 PyPI 发布，
   核验公开元数据，用官方 publisher 验证，然后用 `github-oidc` 发布 Registry。
6. 核验 PyPI 所有权标记和公开 Registry 条目 `io.github.cnkang/qdrant-memory`
   的 0.3.1 版本。只有在公开端点和公开安装验收确认该发行后，才发布公告。

分发 workflow 有一个仅限 tag 的手动 `registry_only` 重试模式。它下载并验证已发布的
PyPI 文件并对之测试，然后重跑 Registry 校验/发布。此过程不上传 PyPI。普通重试同样
复用已验证的现有 PyPI 版本。包依赖、入口、所有权标记或 Registry payload 不匹配时
拒绝继续。

发布需要受保护的 GitHub 环境，并配置必要审核者和仅限 `v*` tag 的部署策略：Runtime
`pypi`、分发 `pypi` 和 `mcp-registry`。发布前核验这些控制，不要绕过。两个项目都已
有发布版本，应复核现有 Trusted Publisher 和必要审核者，不要创建重复的 publisher。

## 0.3.1 的协同适配器发布

版本组合为 Runtime 0.6.0、Python MCP 0.3.1、通用 Skill 0.4.0、托管 launcher
0.1.0-rc.8、WorkBuddy connector 0.2.5 和 DSH bundle 0.1.6。它们独立发布；候选版本
是否公开，须逐一核验对应端点。

1. 核验已公开的 Runtime 0.6.0 及准确依赖。不要重新创建其 tag，也不要再次发布相同版本。
2. 核验已发布的 `skills-20261105.1` 快照中包含 `qdrant-memory` Skill 0.4.0。本次
   MCP 发布不改 Skill 源码，因此不需要新的 Skills 快照。仅在该源码变更时单独发布快照，
   并将真实提交固定到 connector 和 Codex release metadata。
3. 核验 npm 上的 launcher 0.1.0-rc.8 与 `launcher-source.json` 中的 SHA-512 一致。
   Linux、macOS 和 Windows 的公开验收已在
   [Cross-harness run 41994236149](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/41994236149)
   通过。不要重复发布这个不可变 npm 版本。
4. MCP 0.3.1 的 PR 合并且检查通过后，创建 tag `v0.3.1`。workflow 会先构建并测试发行包，
   再发布到受保护的 PyPI 和 MCP Registry 环境。该 release tag 必须包含修正后的 launcher
   完整性固定值。保留旧 `v0.3.0` tag 不动；它的旧 pin 未通过 WorkBuddy 公开发布门禁。
5. 核验 MCP 0.3.1 已出现在 PyPI 和官方 MCP Registry。最终 npm 包发布前先完成 Python 发布。
6. `v0.3.1` tag 会启动 WorkBuddy draft 资产准备。确认构建和附件成功后，再将 connector
   0.2.5 视为准备就绪。仅在检查首次运行后确有需要时，才通过 `workflow_dispatch` 重跑。
7. 从已合并的 main 创建 `dsh-bundle-v0.1.6`，等待 pack 和测试把 tarball 与 checksum
   附加到 Draft Release。最后通过单独的 npm 网页授权发布
   `@cnkang/qdrant-memory-dsh-bundle`。发布后核验公开版本和完整性，再宣布发布完成。
8. 仅当 plugins/qdrant-memory 下没有已跟踪文件变更时，才沿用 Codex 插件候选版当前 ZIP
   和云端验收证据。该目录下任意文件变更后都要重建 ZIP 并重新运行受保护云端验收；
   scripts/build_codex_plugin.py 或 docs/codex-plugin-verification.md 变更后也要重建 ZIP。
   同步三个仓库的当前安装文档和证据。Codex Marketplace 正式提交继续暂停。

## 适配器附件

[WorkBuddy 适配器](../integrations/workbuddy/README.md)增加一个独立的、由 tag 触发的
只读构建和 Draft Release 附件任务。当固定版本的 launcher 尚未在 npm registry 上以
匹配的 integrity 公开时，该 tag 构建拒绝准备资产。其 ZIP 与校验和文件分别记录
Connector、MCP、Runtime、launcher 完整性以及不可变 Skill 的版本。

[DSH Bundle](../integrations/dsh/bundle/README.md)在 `dsh-bundle-release.yml` 中有自己的
`dsh-bundle-v*` tag 流程。它打包仅含配置的 bundle，对照已审核源码校验 payload，准备
tarball 校验和，并把两个文件附加到 Draft Release。在 pack 和测试成功运行后，发布
npm 包 `@cnkang/qdrant-memory-dsh-bundle` 属于维护者步骤。

保持现有受保护 PyPI/Registry 环境、OIDC 门禁和公开验收不变。适配器 workflow 不上传
PyPI 或 Registry 条目。不回溯改造已有发行。手动发布对应 Draft 之前，先等待发布和
适配器准备 workflow。不可变发行要求在发布前完成附件。按 tag 的并发控制串行化附件
运行，且现有 publish.yml 从不写 Releases。

重跑复用匹配的字节。资产冲突或已发布发行缺少资产即拒绝继续。保留 tag/资产，改用
新的已批准发行版，而不是覆盖资产、移动 tag 或重新上传 PyPI 版本。Draft 创建和附件
准备不会取代维护者的发布决定。

该 tag 的 WorkBuddy 构建测试已安装的候选版本，允许在 PyPI 批准前准备 Draft 附件。
它不要求 PyPI 上已存在未公开版本。受保护的 publisher 仍要求在发布后通过公开 uvx
验收。当准确版本可用时，预览要求公开 uvx；否则明确记为 NOT VERIFIED。

2026-10-13 核验的官方参考：

- [发布快速入门](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx)
- [包类型](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx)
- [server.json](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md)
- [官方要求](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/official-registry-requirements.md)
- [GitHub Actions/OIDC](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/github-actions.mdx)

当前 schema 为 2025-12-11。PyPI 所有权验证检查包描述中的
`mcp-name: io.github.cnkang/qdrant-memory`。CLI 名称与 PyPI 标识一致，uvx 可直接运行
它。`mcp` 仍为必需的位置参数，可选 `--home` 位于其前。profile 配置承载模型/维度/
作用域，因此仅靠环境变量声明无法初始化服务器。凭据没有默认值或已提交的值。

官方 publisher v1.8.1 的帮助列出 `validate`，但执行时报 `Unknown command: validate`。
改为在固定源码提交 `11b7b0e274d518b6f449c5ee3518a6151d9848b9` 构建官方 CLI。不要把
旧二进制的误导性零退出状态当作验证通过。官方验证器使用 Registry 校验端点，本地
内置 schema 校验是其补充。
