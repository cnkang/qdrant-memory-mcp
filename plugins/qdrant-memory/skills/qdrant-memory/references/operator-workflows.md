# Operator workflows

These steps are guidance, not permission to change a profile, connect to a
service, download a model, import records or delete data. Act only on the
operation the user requested. The Codex plugin exposes the four scoped memory
MCP tools; profile setup, `doctor`, migration and export use the separately
installed Runtime CLI. Do not turn CLI maintenance into additional MCP tools.

## New isolated local profile

Use this path only when the user wants a new profile and confirms a new
user-controlled directory. The supported Runtime 0.6.0 `setup` command creates a
private embedded profile and initializes its collection. It requires an
explicit embedding-provider choice. For the recommended local CPU option:

```bash
qdrant-memory setup --profile "/absolute/new/profile" --embedding-provider fastembed
```

If the new profile path differs from the launcher's configured location, the
Codex host environment must carry it. The launcher selects
`QDRANT_MEMORY_CODEX_PROFILE` when that variable is set, and otherwise uses
`<root>/profile` under its own runtime root. When the user confirms a profile
outside that path, instruct them to set `QDRANT_MEMORY_CODEX_PROFILE` to the
absolute profile path in the Codex host environment, then reconnect the host
and verify — for example through `qdrant-memory --home "/absolute/new/profile"
status` — that the intended profile is selected before using the memory tools.

This command prepares the pinned CPU model when it is not already cached. Before
running it, ask for explicit permission to download the model and state the
source and size: `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`, revision
`faf4aa4225822f3bc6376869cb1164e8e3feedd0`, **252,138,706 bytes** total, 384
dimensions. Runtime verifies each artifact's pinned size and SHA-256 and
publishes the cache atomically. If the user declines, stop before setup. The
runtime does not silently switch to a cloud provider.

Do not select a path that already has a profile, Ledger or local Qdrant data.
If setup reports that the profile or destination already exists, stop and
inspect it with the user. Never clear or rebuild a collection to make setup
continue. After a successful setup, check the returned `ok`, `ready`, provider,
model and dimensions. Confirm the plugin's four tools are discovered before
using memory. A synthetic add/search check requires the user's authorization to
write test data.

If `qdrant-memory setup --help` is unavailable, explain that the installed
Runtime lacks this setup interface. Do not install or upgrade a Runtime merely
because this skill loaded; follow [runtime setup](runtime.md) only after the
user authorizes installation.

## Connect an existing Qdrant

First confirm that the user is authorized to access the specified Server or
Cloud endpoint, collection and profile. Preserve that collection. Do not use
the new-profile `setup` command for an existing destination and do not run an
initialization path that proposes clearing data.

Use an existing authorized profile/configuration editor. The Runtime config
uses its existing `qdrant.mode`, `collection`, `url_env` and `api_key_env`
fields. Keep `QDRANT_URL`, `QDRANT_API_KEY` and any embedding credential in the
host environment or protected secret store, not in command arguments, prompts,
logs or this Skill. Any non-loopback embedding endpoint must use HTTPS. Cloud
access occurs only when the user explicitly configures a remote endpoint; there
is no implicit cloud fallback.

Before a write, verify the selected scope, collection, embedding provider,
dimensions and fingerprint with the authorized operator. Run the supported
`qdrant-memory --home "/absolute/profile" doctor` only when the user has
authorized a diagnostic against that profile; diagnostics can open or migrate
local Ledger state. If the collection or fingerprint is incompatible, stop and
explain the mismatch. Do not rebuild, re-embed or create a replacement
collection without a separate, explicit migration decision.

## Import Codex native memory

Read [Codex portability](codex.md) first. Inspect only the user-authorized
`CODEX_HOME` and native memory files; do not read chats, credentials or another
agent's profile. Use the Runtime's supported inspection command, then run a
dry-run before asking the user to approve writes:

```bash
qdrant-memory --home "/absolute/profile" codex --codex-home "/authorized/CODEX_HOME" inspect
qdrant-memory --home "/absolute/profile" codex --codex-home "/authorized/CODEX_HOME" migrate --dry-run
```

Review the reported source versions, duplicates, skipped sensitive records and
target scope. Dry-run must report zero destination writes. Only after explicit
approval, run the same migration with `--confirm --verify`. On interruption,
report durable progress and ask before resuming; use the supported `--resume`
path with the same authorized source and target. Do not change scope or retry
failed items automatically.

Native import is read-only with respect to Codex's generated memory files.
Never edit Codex databases or SQLite state. A successful export is
`HANDOFF_PENDING`, not `NATIVE_VERIFIED`; verify adoption only through the
actual Codex client in a fresh chat.

## Export a Codex handoff (not a full-profile backup)

Ask the user to approve an unused output path under an authorized parent
directory. Do not create the destination directory yourself: Runtime creates it
and refuses to reuse an existing handoff. Run both commands from the same
authorized parent directory because explicit output paths must remain within
the invocation directory:

```bash
cd "/authorized/output-parent"
qdrant-memory --home "/absolute/profile" codex export --output "./new-handoff" --confirm
qdrant-memory --home "/absolute/profile" codex verify --output "./new-handoff"
```

Use the supported portable export and verifier; do not copy or edit internal
databases.

This is a Codex handoff workflow: `codex export` writes one scope's portable
JSON/Markdown handoff files, and `codex verify` checks those handed-off files
against their recorded checksums. The export does not include the Ledger,
Runtime or profile configuration, native Codex sources or stored vectors, and
the verifier does not prove a restorable copy of the profile. If the user asks
for a full backup, do not present this export as one; agree on a coordinated
backup procedure that separately backs up the profile directory and the
authorized Qdrant collection before proceeding.

Confirm the command succeeds, record the file and record checksums, and leave
the exported JSON/Markdown available to the user. Preserve the original Codex
memory sources, Qdrant collection, profile, Ledger and model cache. Disabling or
uninstalling the plugin must not delete user data. Deletion or collection reset
is a separate destructive request and requires explicit confirmation of the
exact scope and target.

## Troubleshoot without exposing secrets

Start with the installed CLI's `--help` and the selected profile's
`qdrant-memory --home PROFILE status`. When authorized, run `doctor` and act on
its redacted result:

- **MCP server missing:** confirm the installed plugin and configured local
  server entry, restart the host process once, then confirm MCP initialization
  and discovery of exactly the four supported tools.
- **Runtime or Python import error:** check the executable and installed
  distribution path in the environment actually used by MCP. Do not fall back
  to a developer's global Python or download dependencies silently.
- **CPU model missing or corrupt:** ask permission before preparing/downloading
  it. Runtime verifies hashes and can safely retry an incomplete cache; do not
  delete model or profile data to clear an error.
- **Qdrant unavailable or collection mismatch:** verify the authorized URL,
  collection and fingerprint. Keep API keys in the protected environment and
  never paste them into logs. Do not clear or recreate the destination.
- **`writer_busy`:** close the other authorized writer cleanly and wait for its
  in-flight work to finish. Never remove WriterLease files to force access.
- **`HANDOFF_PENDING`:** the export is available for review, but the Codex
  client has not verified native adoption.

Report the redacted error code, attempted operation and next supported action.
Never include memory text or secret values unless the user asks for that exact
content.
