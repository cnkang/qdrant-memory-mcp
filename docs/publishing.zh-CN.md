# 0.3.0 发布清单

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
5. 确认后创建分发 tag v0.3.0。其 workflow 先构建和测试，再执行受保护的 PyPI 发布，
   核验公开元数据，用官方 publisher 验证，然后用 `github-oidc` 发布 Registry。
6. 核验 PyPI 所有权标记和公开 Registry 条目 `io.github.cnkang/qdrant-memory`
   的 0.3.0 版本。只有在公开端点和公开安装验收确认该发行后，才发布公告。

分发 workflow 有一个仅限 tag 的手动 `registry_only` 重试模式。它下载并验证已发布的
PyPI 文件并对之测试，然后重跑 Registry 校验/发布。此过程不上传 PyPI。普通重试同样
复用已验证的现有 PyPI 版本。包依赖、入口、所有权标记或 Registry payload 不匹配时
拒绝继续。

发布需要受保护的 GitHub 环境，并配置必要审核者和仅限 `v*` tag 的部署策略：Runtime
`pypi`、分发 `pypi` 和 `mcp-registry`。发布前核验这些控制，不要绕过。两个项目都已
有发布版本，应复核现有 Trusted Publisher 和必要审核者，不要创建重复的 publisher。

## 0.3.0 的协同适配器发布

版本组合为 Runtime 0.6.0、Python MCP 0.3.0、通用 Skill 0.4.0、托管 launcher
0.1.0-rc.8、WorkBuddy connector 0.2.5 和 DSH bundle 0.1.6。它们独立发布，源码
中的版本表不等于发布凭据，须分别核验公开端点。

1. 先发布并核验 Runtime 0.6.0，记录真实 release commit、wheel URL、大小和
   SHA-256，再生成 Python 哈希锁。
2. 合并审核通过的 Skill 更新，将真实提交固定到 connector、工作流 checkout 和
   Codex release manifest；保留历史验收记录。
3. 在 Ubuntu 或 macOS 使用 `python scripts/pack_launcher.py --output-dir dist/launcher`
   打包已审核的 launcher。确认输出的 SHA-512 与 `launcher-source.json` 一致，并在发布时
   使用这个确切 tarball。Windows 上 npm pack 得到的 integrity 不同，不能作为正式发布文件。
   将 pin 和 tarball 一并审核，然后合并 MCP 发布 PR。
4. 发布 MCP v0.3.0 并核验 PyPI、Registry；通过独立工作流发布审核后的 Skills
   快照。先完成 Python 包发布，再执行 npm 发布。
5. 使用 `npm publish
   dist/launcher/cnkang-qdrant-memory-launcher-0.1.0-rc.8.tgz --access public --tag next`
   发布审核过的同一文件。把实际 npm 网页授权 URL 交给操作者，由其完成授权，
   不提交 token。核验 npm 的准确版本和 integrity，重跑 Linux、macOS、Windows 的公开 launcher
   验收。源码包测试不能替代公开文件验收。
6. 固定 launcher 已公开后，在 tag `v0.3.0` 上用 `workflow_dispatch` 重新运行
   `Prepare WorkBuddy draft release assets` 工作流。仅在这次运行成功后完成
   WorkBuddy draft 附件。最后通过独立工作流和 npm 授权发布审核后 main 的 DSH
   bundle，核验公开包后再宣布可用。
7. 使用最终固定引用重建 Codex 源码 ZIP 并重跑受保护云端验收，同步三个仓库的当前
   安装文档和证据。Codex Marketplace 正式提交继续暂停。

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
