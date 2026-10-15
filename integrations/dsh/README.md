# DeepSeek Harness integration

See the [English guide](../../docs/dsh-integration.md) or
[中文指南](../../docs/dsh-integration.zh-CN.md).

- `qdrant-memory.cordis.yml`: published Python/uvx overlay. Prepare a separate profile first.
- `managed.cordis.yml`: prepared shared managed-launcher source candidate.
- `bundle/`: configuration-only package using the official `dsh.bundle.patch` contract. It has no native memory engine.
- `package.json` / `package-lock.json`: exact official DSH packages for reproducible integration tests, not a second server.

For a profile-specific bundle installation after preparing the Python backend:

```sh
dsh plugin --profile memory-test add /absolute/path/to/integrations/dsh/bundle
```

Use DSH's official Plugin Manager to enable/disable or remove the bundle. Never
enable it alongside another Qdrant Memory overlay with the same plugin/server
identity. The Desktop test used a separate local configuration-only bundle
pointing to its prepared private CPU profile. Bundle installation itself does
not install Python, download a model or initialize storage.
