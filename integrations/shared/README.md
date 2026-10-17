# Shared service integration preview / 共享服务接入预览

**Unreleased, opt-in.** The distribution remains metadata-only and its public
runtime pin is unchanged. These examples require installing the reviewed Runtime
checkout into a separate virtual environment with `[mcp]`; published 0.3.0 does
not contain `shared-serve`/`shared-mcp`.

Follow [Runtime operations and Hermes/DSH walkthrough](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/codex/shared-memory-service/docs/shared-memory/README.md)
and the [security ADR](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/codex/shared-memory-service/docs/shared-memory/architecture.md).
In a sibling checkout these are `../hermes-plugin-qdrant-memory/docs/shared-memory/`.

1. Provision a new owner profile/collection with one compatible embedding pipeline.
2. Generate distinct high-entropy credentials and explicit fixed-space grants.
3. Start exactly one `qdrant-memory --home OWNER shared-serve --policy POLICY`.
4. Use `mcp.preview.json` for manual stdio registration (including WorkBuddy),
   `dsh.preview.cordis.yml` for an explicitly applied DSH patch, or
   `codex.preview.toml` for Codex. Replace absolute executable paths and inject
   each host's own token securely; never commit real tokens.
5. Discover tool schemas: shared mutations require `request_id`; update/delete
   also require the retrieved `expected_version`. A read-only grant rejects all
   writes in the owner, even when a caller invokes a write tool directly.

The bridges never provision/open a private database and do not duplicate memories.
Only the owner accesses Qdrant/Ledger and performs embedding. Credentials cannot
select identities through tool arguments. Legacy records stay private. The local
HTTP hop is a private API, not a remote HTTP MCP endpoint. No remote agent URL,
OAuth or distributed multi-writer support is claimed.

**Hermes Native Provider compatibility is the first gate.** It continues private
automatic extraction unchanged. Do not register a second qdrant-memory interface
in a Hermes profile already using the Native Provider. Native automatic shared
extraction is planned, not implemented; the walkthrough uses an explicitly
configured MCP-fallback profile or user-authorized operator CLI save.

DSH/WorkBuddy managed provisioning, runtime locks, package versions and defaults
are unchanged. These files are separate preview examples, not a new managed
bundle release. Official SDK process tests verify the protocol; importing these
configs in actual host UIs still needs host acceptance. Do not relabel that test
coverage as native host certification.

中文：通过独立虚拟环境安装审查后的 Runtime checkout，启动唯一 owner，并为各 Agent
显式配置不同 token。使用本目录预览配置手动接入，不修改已有 DSH/WorkBuddy 私有安装。
服务端校验 scope、共享标记、读写权限和版本；旧记录不会自动公开。
Hermes Native Provider 保持兼容和私有，自动提取到共享空间尚未实现，不能注册重复接口。
完整[中文指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/codex/shared-memory-service/docs/shared-memory/README.zh-CN.md)
包含备份、恢复、回滚、安全限制与排障。
