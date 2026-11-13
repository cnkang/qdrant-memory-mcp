# Qdrant Memory native lifecycle adapter for DSH

This Host-only Cordis bundle adds optional automatic recall, memory injection,
and completed-turn capture to DeepSeek Harness. It uses the existing Python
Runtime through its authenticated HTTPS Owner endpoint. It does not open
Qdrant, create a second ledger, or change the four public MCP tools.

The package targets the pinned DSH prerelease `0.2.2-rc.1`, Node.js 24.9 or
newer, and Python Runtime 0.6.2 or newer. Runtime 0.6.2 supports versioned
candidate events and receipt-scoped retries for failed operations. The DSH package
remains private canonical source. The reviewed packer includes it in the existing
`@cnkang/qdrant-memory-dsh-bundle` candidate; do not publish a separate Native
package. See [Bundle storage modes](../bundle/README.md#candidate-storage-modes).

## Install

After installing a compatible Runtime, install this local bundle into one DSH
profile with the official Plugin Manager:

```sh
dsh plugin --profile <profile> add /absolute/path/to/integrations/dsh/native
```

The bundle keeps all three features disabled. Set them through the DSH Plugin
Manager only after the Owner service and capture policy are configured:

```yaml
auto_recall:
  enabled: false
auto_capture:
  enabled: false
memory_injection:
  enabled: false
```

Recall requires both `auto_recall.enabled` and `memory_injection.enabled`.
Capture is independent. Set a value to `true` only for an explicitly approved
profile.

## Configure the Owner connection

Start the existing Runtime Owner with its lifecycle endpoint enabled and an
explicit write grant with a capture rule. Set these environment variables
before launching DSH:

| Variable | Required value |
| --- | --- |
| `QDRANT_MEMORY_RUNTIME_PYTHON` | Absolute path to the Python interpreter with the Runtime installed |
| `QDRANT_MEMORY_DSH_OWNER_URL` | Owner HTTPS endpoint with the exact `/mcp` path |
| `QDRANT_MEMORY_DSH_OWNER_TOKEN` | Provisioned Owner write token; never put it in profile YAML |
| `QDRANT_MEMORY_RUNTIME_CA_FILE` | Optional absolute path to a private CA bundle |

The adapter passes only the Owner token and basic process paths to the Python
child. It launches the child in isolated mode (`-I -S` plus a fixed
site-packages bootstrap) from the interpreter's own directory, so project
content and site startup files cannot shadow the installed Runtime. It does not
inherit unrelated DSH credentials, print request contents, or fall back to
another identity after an authorization failure. The Runtime derives scope from
the Owner grant. Owner setup and TLS policy remain governed
by the [shared security guide](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/shared-deployment-security.md).

## Lifecycle behavior

- Recall runs once at `agent/pre-step` when a new direct user message is
  present. It calls the existing scoped `qdrant_memory_search` tool through
  the Owner and appends a logged user message tagged `qdrant-memory`. Captured
  memory text is JSON-escaped and marked as untrusted data.
- Capture accepts only completed turns. It uses the recorded provider/model
  route, asks DSH's own LLM facade for strict candidate JSON, then sends only
  versioned candidates to the Python Owner. If a candidate explicitly replaces
  an older fact, the request also carries one exact user-text excerpt (at most
  2 KiB); Owner retains it only until the write settles so Runtime can verify
  replacement intent. DSH sends both user and assistant turn text to its own
  extraction call. The Owner event has no assistant field, but its candidates
  can contain facts derived from assistant text and are sent to Runtime. The Runtime performs
  authority checks, scope filtering, relation review, deduplication, ledger
  recovery, and Qdrant writes.
- It ignores tool output, non-user injected messages, interrupted assistant
  output, and all non-completed turn endings. Credential-shaped transcripts
  and candidates are skipped.
- Before capture it awaits DSH's public session flush and reads the validated
  session log. On resume it checks the completed turns that follow the saved
  activation boundary against Owner receipts, batched in eight turns, and skips
  turns already resolved through the durable recovery-progress marker. For
  `ACCEPTED`, `PENDING`, and `FAILED` receipts, it retries by event ID only; the
  Runtime reuses the original immutable candidate plan and, for `FAILED`, queues
  only failed operations. `QUARANTINED` receipts remain for explicit
  Owner-operator recovery. If the retry does not reach `COMMITTED`, the turn
  remains unresolved for a later recovery pass. Candidate data stays
  out of the DSH session log, and the adapter does not re-extract under that ID.
- The queue is bounded. A full queue or a failure before an Owner receipt can
  leave an uncaptured turn in the DSH log. Successful DSH flush plus an Owner
  receipt is the recovery boundary; this adapter makes no zero-loss claim
  before that point.

## Configuration recipes

All three switches are off in the package defaults and bundled patch. The
Plugin Manager controls the selected profile's values. These examples contain
no credentials:

**Everything off (default):**

```yaml
auto_recall:
  enabled: false
auto_capture:
  enabled: false
memory_injection:
  enabled: false
```

**Recall only:**

```yaml
auto_recall:
  enabled: true
memory_injection:
  enabled: true
auto_capture:
  enabled: false
```

**Capture only:**

```yaml
auto_recall:
  enabled: false
memory_injection:
  enabled: false
auto_capture:
  enabled: true
```

**Capture and recall:**

```yaml
auto_recall:
  enabled: true
memory_injection:
  enabled: true
auto_capture:
  enabled: true
```

Recall requires both recall and injection. Capture is independent. A compatible
Runtime Owner must be ready before enabling either write or recall behavior.

## Choose the Owner embedding and deployment

Embedding selection belongs to the Python Owner profile, not DSH. Create a new
Owner destination using the [Runtime embedding guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/local-embedding.md)
and [shared Owner setup](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/README.md).
Runtime 0.6.2 provides the versioned candidate-event and failed-operation retry
contract used by the adapter and is publicly available on PyPI. The commands
below install the released `0.6.2` wheel. On replay, the adapter automatically
retries Owner receipts in `ACCEPTED`, `PENDING`, or `FAILED` state by event ID.
Runtime reuses the stored plan and retries only failed operations; `QUARANTINED`
events still require explicit Owner-operator recovery.

For a new local CPU Owner, explicitly install the Runtime's `local` extra and
create a separate profile:

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote,local]==0.6.2'
qdrant-memory setup --profile /absolute/private/dsh-owner --embedding-provider fastembed --agent-id dsh-owner
```

For an existing Ollama model, the Runtime `local` extra is not needed:

```sh
python -m pip install 'hermes-plugin-qdrant-memory[remote]==0.6.2'
qdrant-memory setup --profile /absolute/private/dsh-owner --embedding-provider ollama --model qwen3-embedding:4b --dimensions 2560 --agent-id dsh-owner
```

For an Owner operated at another HTTPS host, configure a protected destination,
TLS proxy, and profile-scoped grant as described in the [HTTPS Owner guide](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/remote-owner.md).
Set the endpoint and a unique token for each DSH profile in the trusted DSH
process environment. Do not copy the Owner's Qdrant or embedding credentials
to DSH:

```text
QDRANT_MEMORY_DSH_OWNER_URL=https://memory.example.com/mcp
QDRANT_MEMORY_DSH_OWNER_TOKEN=<profile-specific secret from a secret manager>
QDRANT_MEMORY_RUNTIME_PYTHON=/absolute/path/to/compatible-runtime/bin/python
```

Use a separate profile and provisioned token for each unrelated DSH identity.
The Owner determines what that token can read or write. The native adapter does
not combine private data from DSH, Hermes, or WorkBuddy automatically.

## Migration, rollback, and troubleshooting

The published Bundle and Python/uvx overlay remain explicit MCP routes. To try
the native preview later, retain the existing profile and data, add the native
plugin, and leave all switches off until the matching Runtime and Owner grant
are ready. Keep at most one published MCP route (Bundle or overlay) per profile.
The native plugin can be added alongside that one route after the candidate
Runtime is available.

Rollback by disabling the three switches, removing only the native plugin,
then restarting that DSH profile. For example:

```sh
dsh plugin --profile <profile> remove @cnkang/qdrant-memory-dsh-native
```

This does not delete profile files, Owner receipts, Ledger entries, Qdrant
records, or embedding caches. Do not delete those resources as part of plugin
rollback. If capture is pending, check its exact Owner receipt before taking
another action; a transport error alone does not prove that the event failed.

If recall is missing, first confirm both switches are enabled, the profile's
Owner grant allows search, and the endpoint certificate and token work. For
capture, confirm `auto_capture.enabled`, the Runtime candidate-event version,
the Owner write grant, and an active capture rule. The adapter fails open for
ordinary DSH conversation when recall is unavailable and does not queue a
second write under an uncertain event ID.

The adapter runs the Runtime with `-I -S` plus a bootstrap that adds the
interpreter's site-packages without processing `.pth` files or `sitecustomize`,
so `QDRANT_MEMORY_RUNTIME_PYTHON` must name an interpreter whose `site-packages`
contains the Runtime: a dedicated venv, a `uv tool` environment, or a venv
created with `--system-site-packages` whose base interpreter has the Runtime
installed. `--user` and `PYTHONPATH` installs are not visible to the child.

`-I` isolates the working tree, `PYTHONPATH`, and user site-packages; `-S` skips
site initialization, so project-controlled startup code and `.pth` files cannot
run while `QDRANT_MEMORY_DSH_OWNER_TOKEN` is present. The bootstrap honors the
venv's `include-system-site-packages` setting. The interpreter binary and its
installed packages remain a trusted installation; never use a virtual
environment stored inside the DSH project.

## Diagnostics

The plugin keeps in-process counters for recall requests, hits, failures, cache
hits, injected memory count and characters, capture turns seen, eligible and
committed, capture failures, backlog drops, recovery scans, and cumulative
recall latency. The disposer returned by `apply()` exposes a `metrics()` snapshot
for programmatic hosts and tests; DSH has no native status command for it.
Counters never include transcript text or credentials. Runtime receipts expose
status only, so mutation action breakdown and dedupe rate are not available.

## Validation

Run `npm ci` and `npm test` in this directory. These tests exercise bounded
event projection, strict candidate validation, prompt-safe formatting, and
disabled defaults. They use synthetic fixtures and do not represent a live
model, a configured Owner, a GUI check, or a published Runtime acceptance run.
See the [native design](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-native/design.md),
[validation report](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-native/validation.md), and
[中文说明](README.zh-CN.md).
