# Qdrant Memory for Codex

**One Memory. Multiple Agents. No Lock-in.**

Use local durable Qdrant memory without surrendering ownership of your data.
Search, add, update and delete explicitly. Import approved Codex native semantic
memories and leave with readable, checksummed JSON/Markdown. Handoff is pending
until the native client actually adopts the facts; no unsupported native writes.

## Install this candidate

Requirements: Codex with portable plugins, Node 20+, uv, Python 3.11+.
The plugin is 0.1.1; MCP distribution 0.2.9 and Runtime 0.5.5 have separate versions.
This development candidate uses an immutable Runtime adapter source commit recorded
in `release.json`; it is not a new PyPI release. Read that file before installing.
Its `test_evidence` path is relative to the plugin ZIP root (`VERIFICATION.md`).

```sh
codex plugin marketplace add cnkang/qdrant-memory-mcp --ref codex/qdrant-memory-plugin
codex plugin add qdrant-memory@cnkang-memory
```

For a checked-out version, register its repository root instead. Pin a verified
commit with `--ref COMMIT` for reproducible installs. Run the **setup** skill.
Install the private environment only after approving the download:

```sh
uv venv --python 3.11 ~/.qdrant-memory/codex/runtime
uv pip install --python ~/.qdrant-memory/codex/runtime/bin/python -r requirements.txt
~/.qdrant-memory/codex/runtime/bin/qdrant-memory setup \
  --profile "$HOME/.qdrant-memory/codex/profile" --embedding-provider fastembed \
  --agent-id codex --model-cache-dir "$HOME/.qdrant-memory/codex/models"
node launcher.mjs doctor
```

Run these commands from this plugin directory; on Windows use the environment's
`Scripts/python.exe` and `Scripts/qdrant-memory.exe`. Approve approximately 252 MB
for the pinned model download. Cache verification is offline thereafter. CPU
inputs above 128 tokens are rejected explicitly. No model/service cloud fallback.
Native migration sections may require manual semantic shortening before import;
never alter the original Codex source to make a test pass.

For other providers select `--embedding-provider ollama` or `openai-compatible`
and supply explicit model, dimensions, base URL and key **environment variable
name** using Runtime's actual `setup --help`. Keep keys in the operator environment.
Run `doctor` and verify embeddings. Model changes need a new collection/profile,
resumable re-embedding, verification and approved client switch; retain the old one.
Large CPU sections fail rather than silently truncate.

Default paths are under `~/.qdrant-memory/codex`. Trusted host environment can
override `QDRANT_MEMORY_CODEX_ROOT`, `QDRANT_MEMORY_CODEX_PROFILE` and
`QDRANT_MEMORY_CODEX_EXECUTABLE` using absolute canonical paths. Set them in the
actual Codex host environment, then restart/reconnect the plugin.
For concurrent agents use the authorized Runtime Shared Owner via
`QDRANT_MEMORY_CODEX_OWNER_URL` and `QDRANT_MEMORY_SHARED_TOKEN`. This chooses
`shared-mcp` instead of opening private storage. Never point independent ledgers
at one live collection or change Hermes settings to make Codex work.

## Import, backup and exit

```sh
qdrant-memory codex inspect --codex-home /canonical/approved-codex-home
qdrant-memory --home /canonical/profile codex migrate --codex-home /canonical/approved-codex-home --dry-run
# Review source preview, hashes, skipped sections, target scope, then approve:
qdrant-memory --home /canonical/profile codex migrate --codex-home /canonical/approved-codex-home --confirm --verify
qdrant-memory --home /canonical/profile codex migrate --codex-home /canonical/approved-codex-home --confirm --resume --retry-failed --verify
qdrant-memory --home /canonical/profile codex export --output ./new-handoff --confirm
qdrant-memory codex verify --output ./new-handoff
```

Read-only v1/v2 imports retain source provenance and deterministic IDs. Code,
likely credentials, raw chats and supporting logs are excluded. Review sensitive
content manually; pattern detection is not a complete privacy classifier. Use
`--source-version v1` or `v2` to narrow sources. Unknown layouts are reported;
repeat `--heading 'Exact Topic'` to select source topics/categories, including
project-named headings, while retaining the profile's fixed destination scope.
Configuration flags do not establish effective per-client memory enablement.
Output paths must be inside the invocation directory. Existing bundles cannot
be overwritten. Standard Runtime JSON export/import stays available for other
harnesses; new native adapters should use their documented interfaces.

To return to Codex native memory, verify the bundle, review facts, enable native
memory and ask the actual client to remember approved facts. Recheck in a new
chat. This may use that client's model processing path; approve private content
first. Native bulk import is not provided. Status remains HANDOFF_PENDING.
AGENTS.md is not native memory. Keep Qdrant until adoption is confirmed.

Disable the plugin in Codex settings, or remove its cache:

```sh
codex plugin remove qdrant-memory@cnkang-memory
```

Uninstall never deletes Qdrant, native data, model cache or exports. Roll back by
reinstalling the previous exact plugin commit and selecting the retained profile;
do not reset the collection. JSON/Markdown remains readable without any plugin.

## Release status and privacy

See the repository's `docs/codex-plugin-verification.md` for executed evidence
and remaining gates. Local processing is the default. Cloud Qdrant/embeddings
require explicit configuration and consent. No telemetry or automatic capture
is added. Report vulnerabilities privately through the repository security
contact, not in an issue containing private memory or credentials.

This is a GitHub Marketplace candidate, not an approved OpenAI public-directory
listing. Public submission requires partner allowlisting, fully bundled and
reviewed local runtime/dependencies, fresh Desktop verification, privacy/support
metadata and review. No public registry, GitHub Release or tag is published here.
