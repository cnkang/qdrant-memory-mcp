# 0.1.3 补丁发布清单

[English](publishing.md) | [简体中文](publishing.zh-CN.md)

Runtime、PyPI 和 MCP Registry 发布须获得操作员明确授权。发布前在 release PR
中准备版本化的包及 Registry 元数据、README 示例和发布说明。
`verify_metadata.py` 要求 README 安装版本与发行包版本一致，PyPI 文件不可覆盖。
示例表示目标发行版本，不代表该版本已公开可用。执行固定版本安装命令前，
须确认对应公开版本；只有公开端点及安装验收通过后，才宣布发布完成。

1. 核验已公开的 Runtime 0.2.2 及准确依赖。本次分发补丁不重新创建
   Runtime tag，也不重新发布 Runtime。
2. 核对两个已有 PyPI Trusted Publisher：仓库分别为
   `cnkang/hermes-plugin-qdrant-memory` 和 `cnkang/qdrant-memory-mcp`，
   workflow 均为 `publish.yml`，环境均为 `pypi`。不创建重复配置。
3. 通过现有受保护 GitHub 环境审核，复用已验证的 Runtime 0.2.2 公开 PyPI 文件。
   tag 必须指向 main 的提交，且与包版本匹配；不覆盖已有 tag 或发行文件。
4. 在新环境中仅使用准确的公开 Runtime 版本，对 MCP wheel 和 sdist 运行
   SDK 1.x、2.x 的完整验收。
5. 检查通过并获得授权后创建 MCP `v0.1.3` tag。workflow 在受保护 PyPI 发布前
   构建并验证文件，然后核对公开包、使用官方 publisher 验证 Registry 元数据，
   并通过 `github-oidc` 发布。
6. 验证 PyPI 所有权标记、公开 Registry 中
   `io.github.cnkang/qdrant-memory` 的 0.1.3 版本和公开安装流程，再发布公告。
   Skill 来源保持已审核的不可变提交；仅在确有内容变化时更新。

发布环境必须保留必要审核者及仅允许 `v*` tag 的规则：Runtime 的 `pypi`，
MCP 的 `pypi` 和 `mcp-registry`。不绕过门禁。

Registry 发布可从版本 tag 启动 `registry_only` 重试。它下载并验证已经公开的
不可变 PyPI 文件，运行验收，再重试 Registry，不重新上传 PyPI。普通重试也会
复用经过验证的已有版本；依赖、入口、所有权标记或 Registry payload 不匹配时拒绝继续。

Registry schema 为 `2025-12-11`。PyPI 包描述保留
`mcp-name: io.github.cnkang/qdrant-memory` 所有权标记。`mcp` 为必要位置参数，
可选 `--home` 放在其前；profile 配置包含模型、维度和作用域，不能仅靠环境变量
完成初始化。凭据不写入默认值或版本控制。

使用固定源码修订 `11b7b0e274d518b6f449c5ee3518a6151d9848b9` 构建官方 publisher。
v1.8.1 二进制的帮助列出 `validate`，但执行时可能返回 `Unknown command: validate`；
不能把其零退出状态视为验证成功。官方验证与仓库内 schema 校验相互补充。
官方协议及发布参考链接见[英文指南](publishing.md)。
