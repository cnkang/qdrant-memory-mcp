# DeepSeek Harness integration

See the [English guide](../../docs/dsh-integration.md) or
[中文指南](../../docs/dsh-integration.zh-CN.md).

- `bundle/`: the configuration-only Bundle (`@cnkang/qdrant-memory-dsh-bundle`)
  for the official `dsh.bundle.patch` contract. It connects the public managed
  launcher through the official `@deepseek-ai/dsh-mcp-client`. Install it with
  `dsh plugin --profile <name> add`. Backend preparation is an explicit step.
- `qdrant-memory.cordis.yml`: published Python/uvx overlay for `--patch` use.
  Prepare a separate profile first.
- `package.json` / `package-lock.json`: exact official DSH packages for
  reproducible integration tests, not a second server.

Use one route per profile. Never enable the Bundle and the overlay together.
