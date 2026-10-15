# Hermes compatibility

Existing Hermes users can keep using the native Qdrant Memory plugin and their
current profile, model and configuration. The new WorkBuddy/DSH adapters are
opt-in and do not register a second Hermes memory provider, import its profile,
change its embedding defaults or call its lifecycle callbacks.

The shared Runtime remains in
[`hermes-plugin-qdrant-memory`](https://github.com/cnkang/hermes-plugin-qdrant-memory).
This repository adds process/configuration adapters only. The published MCP
dependency remains unchanged. Optional managed CPU setup uses an immutable
source candidate separately from existing Python environments.

Hermes still owns automatic turn extraction and prefetch. The four MCP tools
provide explicit operations. Do not enable both the native plugin and a second
MCP connection against the same embedded profile. Close its current owner before
maintenance or migration; do not bypass WriterLease.

Changes to shared Runtime behavior require its full Hermes regression gate:
native provider/lifecycle, inherited/default models, Ollama/cloud embedding,
fingerprint compatibility, scope, WriterLease, ledger/recovery, MCP and restart
persistence. External services and actual models have separate acceptance gates;
skips are unverified capabilities. Adapter tests do not replace those gates.
See [validation](dsh-validation.md) for this change's evidence and limits.
