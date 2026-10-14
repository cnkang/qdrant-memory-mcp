# WorkBuddy MCP + Skill connector

This adapter packages the existing Python stdio MCP and an upstream-generated
Skill. It does not implement memory, change Runtime, or add Python modules to
the metadata-only PyPI wheel. Explicit search/add/update/delete remain the four
MCP tools. Hermes automatic extraction and prefetch remain Hermes features.

## Requirements and installation behavior

WorkBuddy 4.24.0 or newer is required for bilingual names and examples.
The shipped command is `uvx --from qdrant-memory-mcp==0.1.2 qdrant-memory-mcp mcp`.
Install uv/uvx and Python 3.11+ beforehand, ensure uvx is on the desktop app's
PATH, and warm the pinned package before connecting. Network installation can
exceed the 30-second connection timeout. Tools should respond within 30 seconds;
large embedding requests depend on the configured service.

This is a **preconfigured environment** connector. No fully managed or one-click
installation has been verified. The official MCP schema currently manages only
Node.js. A Node wrapper still needs a trustworthy Python/uv installer, secure
platform binary verification and profile setup; it adds no useful MVP capability.
No other documented MCP installation hook solves those steps. `preAuth: cli` is
an authentication flow, not a generic installation workaround. We do not add it,
a CLI connector, an npm package, or a remote gateway.

Official references checked on 2026-10-14:
[connector (Chinese)](https://open.workbuddy.cn/docs/connector),
[connector (English)](https://open.workbuddy.cn/en/docs/connector),
[Skill](https://open.workbuddy.cn/docs/skill).
The documented connector folder is preserved as one ZIP root. ZIP import and
market review remain separate from generic MCP SDK acceptance.

## Immutable Skill and versions

`skill-source.json` pins `cnkang/skills` commit
`405d5664a6b682adefbaef7513653607a420e757`, Skill 0.2.5. Its reviewed WorkBuddy
builder performs frontmatter conversion, license/resource selection and local
link checks. This adapter verifies origin, exact clean checkout, version and
unchanged Markdown body. No second canonical `SKILL.md` is maintained here.

Connector 0.1.0, MCP 0.1.2, Runtime 0.2.2 and Skill 0.2.5 are independent.
`provenance.json` records all versions and source SHA. For a future MCP release,
update the checked-in `mcp.json` pin alongside normal package/Registry metadata;
the builder rejects drift. Updating the Skill pin also requires updating both
WorkBuddy workflow checkout SHAs and reviewing upstream code/resources.

## Build a preview

From this repository, use a fresh canonical source checkout and private build
environment (the Skill builder needs PyYAML):

```sh
git clone --no-checkout https://github.com/cnkang/skills.git .workbuddy-skill
git -C .workbuddy-skill checkout --detach 405d5664a6b682adefbaef7513653607a420e757
python3 -m venv .workbuddy-env
.workbuddy-env/bin/python -m pip install 'PyYAML==6.0.3'
.workbuddy-env/bin/python integrations/workbuddy/build.py --check
.workbuddy-env/bin/python integrations/workbuddy/build.py
unzip -l dist/workbuddy/*-preview.zip
cd dist/workbuddy && shasum -a 256 -c *.sha256
```

Windows uses `.workbuddy-env/Scripts/python.exe`; Python 3.11+ is required.
`--skill-root /path/to/fresh/checkout` selects an existing pinned checkout.
The builder needs no Qdrant, profile or credentials. It emits only ZIP/checksum
under `dist/workbuddy`, rejects symlinks/unsafe resources, uses sorted STORE ZIP
members with fixed dates/modes, and refuses differing existing output bytes.
`--check` builds twice in disposable directories and compares exact bytes.

```text
qdrant-memory-workbuddy/
  connector-meta.json
  mcp.json
  icon.svg
  provenance.json
  skills/qdrant-memory/
    SKILL.md
    LICENSE
    references/...
    scripts/...
```

No generated Skill, ZIP, database or profile is committed. The preview workflow
uses read-only permissions and retains `workbuddy-connector-preview` for 14 days.

## Configure storage before MCP connection

Dependency installation, profile configuration, embedding service readiness,
storage initialization and MCP connection are separate steps. Without `--home`,
Runtime uses `~/.qdrant-memory`. Never overwrite an existing profile or initialize
an existing collection without the owner's authorization. For an isolated test,
choose a new private profile and add `--home /private/test/profile` before `mcp`
in a local custom MCP configuration. Do not ship that absolute path.

For a new authorized local profile, create `qdrant-memory.json` privately:

```json
{
  "scope": {"user_id": "local-user", "agent_id": "workbuddy"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "provider": "ollama", "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434", "dimensions": 2560
  }
}
```

Use the actual installed model and its dimensions. Install/start Ollama separately.
Run the pinned launcher with `init`, then `doctor`, in place of `mcp` only for the
authorized target. Check service readiness before connecting.

For self-hosted or Cloud storage use Runtime's documented server/cloud profile
configuration and the actual collection/scope/embedding pipeline; see the
[canonical setup reference](https://github.com/cnkang/skills/blob/405d5664a6b682adefbaef7513653607a420e757/qdrant-memory/references/runtime.md)
and [Runtime configuration](https://github.com/cnkang/hermes-plugin-qdrant-memory).
Supply `QDRANT_API_KEY` and `EMBEDDING_API_KEY` through a private process environment
or secret manager. Never put credentials in this package, command arguments,
examples or logs. `QDRANT_URL` alone is not profile initialization. Cloud's
database URL is not an MCP endpoint.

The official Token form can inject `${VAR}` into stdio env, with password fields
and exact schema keys. It cannot create/configure a Runtime profile. This MVP
has no placeholders, `auth_mode`, or `token-schema.json`, so local no-auth use
is not blocked by remote credentials. Cloud is operator-configured, not a
verified WorkBuddy Token form experience. A future Cloud connector must verify
the whole form-to-profile configuration path before declaring managed support.

In a new, authorized Cloud profile the storage section is, for example:

```json
{"qdrant": {"mode": "cloud", "collection": "authorized_collection",
            "url_env": "QDRANT_URL", "api_key_env": "QDRANT_API_KEY"}}
```

Keep the scope and embedding sections as well. Set `QDRANT_URL` to the cluster's
HTTPS database URL and inject `QDRANT_API_KEY` privately into the launched process.
Use `mode: server` for self-hosted Qdrant instead. Runtime validates the URL and
requires a Cloud API key. A custom WorkBuddy MCP config can inherit or inject
private env values; do not put that private config in the distribution ZIP.

Scope is operator-configured; client names/tool arguments cannot switch identity.
Separate users need separate profiles/process credentials. Embedded storage and
WriterLease require exclusive profile access; close Hermes's writer before
opening the same profile through WorkBuddy. Independent profiles do not provide
a distributed lease for the same remote collection.

## Connection and troubleshooting

Use WorkBuddy's reviewed connector import path when available, or use custom MCP
to test the generated `mcp.json` configuration in an isolated profile. Verify all
four tools before using synthetic data. Skill installation does not initialize
storage or authorize memory writes. Ask WorkBuddy's platform team for the
submission/import mechanism if the client exposes only custom MCP configuration.

If uvx is unavailable, install it and restart WorkBuddy so it inherits PATH. Warm
dependencies before reconnecting. Embedding failures can prevent startup and
return a sanitized error type; run `doctor` privately to diagnose configuration.
Invalid credentials must fail safely. Do not debug by publishing profile files.
If WriterBusyError occurs, stop the competing authorized writer and retry;
never bypass the lease or modify the ledger directly.

## Acceptance matrix

SDK acceptance uses synthetic loopback embeddings and disposable embedded
storage. Existing distribution CI covers macOS/Linux/Windows and SDK 1.x/2.x.
The preview job additionally executes the actual pinned public uvx command.
Neither is WorkBuddy GUI acceptance.

| WorkBuddy client acceptance | Status |
|---|---|
| Import ZIP; bilingual metadata/icon/Skill resources | NOT VERIFIED |
| Install dependencies and configure isolated profile | Manual prerequisite |
| Connect; discover exactly four tools | NOT VERIFIED |
| Search/save/update/delete selected synthetic records | NOT VERIFIED |
| Restart; retrieve persisted synthetic records | NOT VERIFIED |
| Missing embedding and invalid API key fail safely | SDK tested; GUI NOT VERIFIED |
| Same-profile Hermes WriterLease refusal | SDK tested; GUI NOT VERIFIED |

Record actual client version, OS, isolation path and observations before marking
any GUI row passed. Do not use existing personal memory for acceptance.

## Future release and recovery

Only an approved next MCP version tag matching package metadata and merged main
can trigger release preparation. `workbuddy-release.yml` builds/tests with
`contents: read`; a dependent minimal `contents: write` job validates downloaded
ZIP/checksum/provenance and attaches assets to Draft. It never executes upstream
Skill code, publishes the Draft, touches PyPI/Registry, or moves tags.

The existing protected `pypi`/`mcp-registry` environments and OIDC flow remain
unchanged. Those jobs do not edit GitHub Releases, so they do not race this
per-tag serialized Draft workflow. Maintainers must wait for both workflows and
verify public-install/Registry acceptance and assets before publishing the Draft.
Do not publish while attachment preparation is running. Immutable GitHub releases
require all attachments before publication.

Reruns compare bytes and reuse matching assets. A conflict, or published release
missing attachments, fails without replacement. Investigate toolchain/source
drift, preserve old assets/tags, and prepare a new approved release if necessary.
Rollback means selecting the previous reviewed connector/package/profile backup;
never republish an existing PyPI version or rewrite a release tag. Existing 0.1.2
is not retrofitted. This PR creates no formal tag or release.
