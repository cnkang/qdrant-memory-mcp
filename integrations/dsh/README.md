# DeepSeek Harness integration

See the [English guide](../../docs/dsh-integration.md) or
[中文指南](../../docs/dsh-integration.zh-CN.md).

- `bundle/`: the unified Host Bundle (`@cnkang/qdrant-memory-dsh-bundle`)
  for the official `dsh.bundle.patch` contract. It connects the public managed
  launcher by default and can explicitly select one HTTPS Owner for tools and
  opt-in Native lifecycle. Install it with
  `dsh plugin --profile <name> add`. Backend preparation is an explicit step.
- `qdrant-memory.cordis.yml`: published Python/uvx overlay for `--patch` use.
  Prepare a separate profile first.
- `native/`: unpublished, opt-in Cordis lifecycle adapter for the exact
  `@deepseek-ai/dsh@0.2.2-rc.1` lane. It requires the companion Runtime
  candidate-event support and keeps automatic recall, capture, and memory
  injection disabled by default. See [native setup](native/README.md),
  [中文设置](native/README.zh-CN.md), and the
  [validation report](../../docs/dsh-native/validation.md).
- `package.json` / `package-lock.json`: exact official DSH packages for
  the official `0.2.2-rc.1` integration tests, not a second server.

Use one published MCP route per profile. Never enable the Bundle and the
overlay together. Prefer the unified Bundle for Native upgrades; keep the
private Native source package unpublished. See [release evidence and remaining
gates](../../docs/dsh-native/release-readiness.md).
