# Shared service integration / 共享服务接入

Read [deployment security](../../docs/shared-deployment-security.md) before production use.
Client bridges receive only Owner tokens.
The Owner retains database write credentials.
Destination protection and shared doctor require Runtime 0.5.0.
Runtime 0.4.0 does not provide these features.

**Opt-in.** The distribution remains metadata-only and pins Runtime 0.5.0.
Install the published Runtime into a separate virtual environment with `[remote]`, which adds the HTTPS listener dependencies.
Runtime 0.5.0 provides `shared-serve`, `shared-mcp`, `remote-serve` and `remote-mcp`.

Install the Runtime in an isolated environment:

```sh
python3 -m venv /absolute/path/shared-runtime-env
/absolute/path/shared-runtime-env/bin/pip install 'hermes-plugin-qdrant-memory[remote]==0.5.1'
```

Follow the [Runtime operations and Hermes/DSH walkthrough](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/README.md).
Read the [security ADR](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/architecture.md).
In a sibling checkout these are `../hermes-plugin-qdrant-memory/docs/shared-memory/`.

1. Create a new Owner profile and collection with one compatible embedding pipeline.
2. Generate distinct high-entropy credentials and explicit fixed-space grants.
3. Start exactly one Owner.
   Local clients use `qdrant-memory --home OWNER shared-serve --policy POLICY`.
   Remote clients use `remote-serve` behind a same-host TLS proxy.
   Pass the exact public host with `--allowed-host`.
4. Select the configuration example for your host.
   Use `mcp.preview.json` for manual stdio registration, including WorkBuddy.
   Use `dsh.preview.cordis.yml` for an explicit DSH configuration change.
   Use `codex.preview.toml` for Codex.
5. Replace the example executable paths.
6. Supply each host's token through its secure credential configuration.
7. Do not commit real tokens.
8. Read the tool schemas.
9. Supply `request_id` for each shared mutation.
10. For updates and deletions, also supply the retrieved `expected_version`.

The Owner rejects writes that use a read-only grant.
This rule also applies to direct calls to write tools.

The bridges do not create or open a private database.
They do not duplicate memories.
Only the Owner accesses Qdrant and the Ledger or creates embeddings.
Tool arguments cannot select a credential identity.
Existing records stay private.

The `shared-serve` private API stays local HTTP and loopback-only.
Remote clients use the separate HTTPS MCP endpoint that Runtime 0.5.0 adds, each with its own device credential.
One Owner serves one destination.
OAuth and multiple distributed writers remain unsupported.

The released Hermes Native Provider continues automatic private extraction.
Do not register a second qdrant-memory interface in a Hermes profile that already uses the Native Provider.
Runtime 0.5.0 provides opt-in automatic shared extraction through a Native Hermes Owner or a standalone Owner.
The walkthrough uses a separate MCP profile or an authorized operator CLI save command.
This release supports additional capabilities in the [Owner capability summary](../../docs/universal-owner-status.md).

DSH and WorkBuddy retain their managed setup and private defaults. These
files are separate examples. Official SDK process tests verify the protocol.
These tests do not verify configuration imports through host user interfaces.
Do not describe protocol test results as native host certification.

## Remote HTTPS MCP

The `*.remote-preview.*` examples use the official MCP-to-MCP `remote-mcp`
bridge over HTTPS. Runtime 0.5.0 provides that bridge.
The example file names keep their original suffix.
They keep TLS verification enabled.
They do not contain database or model credentials.

`mcp.remote-preview.json` uses WorkBuddy's stdio configuration and the `${QDRANT_MEMORY_REMOTE_TOKEN}` credential reference.
Supply this value through WorkBuddy's secure credential configuration.
See the [WorkBuddy connector documentation](https://open.workbuddy.cn/en/docs/connector).
Other MCP clients can require different syntax.
For another client, use its documented credential-reference syntax.
Omit `env` only if the client securely forwards the variable to the child process.

Do not commit a token in place of the reference.

These examples do not verify host user interfaces or automatic memory.
Hosts with native HTTP support can connect directly to `https://<owner>/mcp` with a separate credential.
This release does not support OAuth or browser authentication.
See [Pi's separately verified lifecycle adapter](../pi/README.md).

## Summary / 摘要

Install Runtime 0.5.0 in a separate virtual environment.
Start one Owner with a separate token for each client.
One Owner serves one destination.
Multiple distributed writers remain unsupported.
Use the example for your host.
The examples do not change existing private DSH or WorkBuddy installations.
The Owner checks scope, sharing flags, permissions, and record versions.
Existing records stay private.

Runtime 0.5.0 preserves private Hermes Native Provider behavior and adds explicit shared capture rules.
Do not register a duplicate interface.
The HTTPS MCP endpoint requires Runtime 0.5.0 and TLS verification.
Its credential-reference syntax depends on the host.
This release does not support OAuth or browser authentication.
Protocol tests do not verify host user interfaces or automatic memory.

The [Runtime guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/README.md)
covers backup, recovery, rollback, security limits, and troubleshooting.

在独立虚拟环境中安装 Runtime 0.5.0。
启动一个 Owner，并为每个客户端配置独立 token。
一个 Owner 只服务一个 destination。
不支持多个分布式 writer。
使用对应宿主的示例配置。
示例不会更改已有的 DSH 或 WorkBuddy 私有安装。
Owner 校验 scope、共享标记、权限和记录版本。
已有记录保持私有。

Runtime 0.5.0 保留 Hermes Native Provider 的私有行为，并新增显式的共享捕获规则。
不要注册重复接口。
HTTPS MCP 端点需要 Runtime 0.5.0，并必须验证 TLS。
凭据引用语法取决于宿主。
本版本不支持 OAuth 或浏览器认证。
协议测试不能验证宿主用户界面或自动记忆。

[Runtime 中文指南](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/README.zh-CN.md)
包含备份、恢复、回滚、安全限制和排障说明。
