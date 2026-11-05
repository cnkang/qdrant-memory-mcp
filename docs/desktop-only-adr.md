# Desktop-only package architecture ADR

Date: 2026-11-06
Status: **BLOCKED pending a verified Desktop/Creator launch contract**

## Decision and blocker

Keep one Python Runtime and one set of four MCP schemas. No final Desktop ZIP
architecture is selected yet: the current Portable MCP schema exposes one
stdio command and does not document an OS/architecture selector or multiple
platform payloads. A universal ZIP therefore needs a dispatcher, but its Node
runtime availability on a clean Desktop install is unverified. A
platform-specific archive would avoid dispatch, but the current submission
docs do not confirm that one plugin release can supply and select separate
archives per platform. Confirm one of these host behaviors through an approved
test route before implementing the final packaging target.

If a platform-specific archive is supported, the lowest-risk candidate is a
per-platform bundle containing a standalone Python interpreter, the existing
Runtime and MCP distributions, all resolved dependency wheels and their hashes.
If only one universal ZIP is supported and Desktop guarantees a local Node
command, the same bundle contents could be selected by a small Node launcher.
Neither condition is verified. Do not implement or label either as a chosen
submission architecture until the launch and Creator configuration are tested.
The read-only Creator 0.1.1 file inspection showed a normalized `.mcp.json`
with `env: {}` while the Codex source overlay declares eight `env_vars` names;
there is no verified configuration mapping for the current candidate.

## Evaluated alternatives

| Option | Compliance and reliability | Platform and size | Decision |
|---|---|---|---|
| Bundled Python + pinned wheels | Includes the local server and Python dependencies; can run offline; requires per-platform native wheels and a supported launch route | One interpreter/wheel set per platform; actual archive size is not measured | Preferred bundle contents only after platform selection is confirmed |
| Separate prebuilt Runtime per platform | Reuses the existing Runtime and can minimize irrelevant binaries per download | Lowest platform-specific archive size; the portal's per-platform selection behavior is unconfirmed | Viable only if the official package flow supports multiple platform archives |
| `uv` / lockfile installation on first run | Exact pins and hashes can improve provenance | Still downloads server dependencies after install and is not offline; does not satisfy the conservative reading of “include the server and its dependencies” | Reject for the submitted ZIP |
| Existing managed Node launcher | Reuses secure bootstrap, hash checks and private environment patterns | Its purpose is to download Python, wheels and the model during setup; that is not a bundled server package | Reuse design patterns only; do not reuse its download-at-install behavior |
| Frozen executable built from the existing Python Runtime | Can embed the interpreter and dependencies without rewriting memory behavior; retains one codebase | Requires separate native build per OS/architecture and has less transparent runtime SBOM/debugging; still needs a supported archive selection path | Evaluate only if a per-platform package flow is confirmed |
| Pure Node rewrite or independent second Runtime | Could avoid a Python interpreter at launch | Duplicates Qdrant, embedding, scope, ledger, recovery and lease behavior; violates the one-Runtime boundary | Reject |

## Platform and package tradeoffs

| Target or constraint | Required bundle contents | Evidence and current status |
|---|---|---|
| macOS Apple Silicon | arm64 standalone Python, MCP/Runtime wheels and every transitive native wheel | Runtime and CPU-model checks passed on this host; no standalone interpreter bundle or Desktop install has been built. |
| macOS Intel | x86_64 standalone Python and x86_64 native wheels | No Intel host was available. Runtime and Desktop package are **NOT VERIFIED** for Intel. |
| Windows x64 | Windows embeddable/standalone Python, Windows native wheels and launcher dispatch | Runtime CI contracts and standalone MCP tests passed on Windows x64; no bundled Desktop ZIP or GUI install was tested. |
| Linux x64 | Linux standalone Python and glibc-compatible wheels | Runtime CI passed on Ubuntu x64; this is a development target and does not establish ChatGPT Desktop support. |
| Offline launch | Server, interpreter and all Python dependencies must be in the archive | The proposed bundle can meet this. Current source ZIP depends on installed Python and external package pins, so offline Desktop launch is **NOT VERIFIED**. |
| Artifact size | One runtime and wheel set per supported OS/architecture; model data considered separately | No Desktop archive size exists. CPU model weights alone total 252,138,706 bytes; do not add them to ZIP until OpenAI's model-asset requirement is clarified and package size is measured. |
| Reproducibility and supply chain | Immutable source commits, wheel hashes, interpreter hashes, SBOM, licenses and archive hash | The source package pins component commits, but no full wheel lock, runtime hashes, SBOM or reproducible Desktop build exists. |
| Security and upgrades | Private staging, no secret arguments, strict platform selection, data directory outside plugin root | Existing launcher patterns can be reused, but final archive path safety, upgrade, rollback and uninstall have not been verified. |
| Runtime compatibility | Keep existing Python Runtime and four tool schemas | This avoids a second Qdrant/embedding/ledger implementation. No Runtime changes are required for the proposed bundle. |

The separate `build-desktop-only-plugin` target has **not been implemented**.
Only the existing source Marketplace archive target is available today. Its
78,831-byte macOS build has no Python executable, wheel or model; this size is
not representative of a Desktop bundle.

## Model delivery

The default CPU model is a separately prepared data asset, not a Python
distribution. Runtime 0.6.0 pins FastEmbed 0.9.1, model
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, Qdrant artifact
revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`, 384 dimensions and
252,138,706 bytes across five files. Runtime streams HTTPS downloads, checks
exact sizes and SHA-256 values, stages privately, and atomically publishes the
complete cache. Setup is explicit and a missing model does not trigger cloud
fallback.

The current official Desktop-only wording requires the server and its
dependencies in the package but does not say whether model weights must also be
inside the ZIP. Keep model preparation as a separate, user-approved step only
if Directory review accepts immutable model assets as runtime data. Record this
as a review uncertainty, not as a verified exception. Do not call the existing
lightweight Marketplace ZIP a Desktop-only package.

## Reproducibility and supply chain

The package builder must require exact source commits, immutable Python and
wheel artifacts, SHA-256 for every included executable and dependency, per-target
SBOM and license notices, and an archive-level SHA-256. It must reject symlinks,
path traversal, duplicate archive members, unlisted files and any credential
material. If platform build tools introduce nondeterminism, require a clean
rebuild from the same pinned sources and compare the dependency/artifact hashes;
record any byte-level variance.

No multi-platform runtime bundle, complete dependency lock, SBOM, or Desktop ZIP
has been produced in this task. Do not treat the proposed bundle contents as a
resolved package architecture or claim package readiness.

## Official references

- [Plugin structure and bundled MCP servers](https://developers.openai.com/plugins/build/plugins)
- [Local MCP server packaging](https://developers.openai.com/plugins/deploy/desktop-only)
- [Portable MCP schema 1.0.0](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json)
- [Portable plugin schema 1.0.0](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json)
