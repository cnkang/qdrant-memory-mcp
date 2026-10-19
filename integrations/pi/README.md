# Pi Owner lifecycle adapter (source preview)

Requires a reviewed unreleased Runtime checkout supplying `remote-call` and
`remote-event`; the distribution's released 0.4.0 Runtime pin is unchanged.
This adapter is off by default. It uses Pi's public `session_start`,
`before_agent_start`, `context`, `turn_end` and `session_shutdown` extension hooks.
Tested with the actual Pi 1.3.0 session runtime and deterministic model responses;
user UI and real-model quality are separate, unverified acceptance items.

Explicitly install `owner-memory.mjs` through Pi's normal extension configuration.
Configure the reviewed Runtime Python, endpoint and a secret-manager injected
independent credential:

```sh
export QDRANT_MEMORY_RUNTIME_PYTHON=/path/to/reviewed-runtime/bin/python
export QDRANT_MEMORY_OWNER_URL=https://memory.example.com/mcp
export QDRANT_MEMORY_AUTO_RECALL=1
export QDRANT_MEMORY_AUTO_CAPTURE=1
```

Provide `QDRANT_MEMORY_REMOTE_TOKEN` through the host's secret environment, never
in a command line or repository file. Optional `QDRANT_MEMORY_CA_FILE` trusts a
private CA; TLS verification remains mandatory. Do not put a Qdrant key on Pi.
Omit the capture flag for read-only clients. A private credential captures private
memory by default. Shared/project capture additionally requires an Owner-side
`capture_rule_id` approved for the intended project; the extension cannot create
that permission or choose a different space through payloads.

To capture private memory while recalling an authorized project, inject a separate
read-only `QDRANT_MEMORY_RECALL_TOKEN`. The adapter uses it only for recall;
`QDRANT_MEMORY_REMOTE_TOKEN` still binds capture and its durable outbox. Both
credentials are independently scoped and revocable. No tool argument supplies scope.

The Owner must explicitly enable its `/events` lifecycle extension with an
extraction model. The adapter never extracts, embeds or writes a database. It
reads only current permitted hook content, not files or historical conversations.
Its own pending event entries are persisted through Pi's official session API and
retried with identical event IDs after resuming that session. A full 128-event
outbox pauses new capture; restore Owner connectivity before continuing capture.
Failed events remain in the current session outbox. They are not automatically
read from other sessions. Deleting a pending local entry is an explicit Host
operation, not an Owner data deletion. An already durable accepted Owner event
finishes its recorded plan; use authorized CRUD to delete resulting memories.

Recall is fetched in the official ephemeral `context` hook for each model request.
Old adapter recall messages are removed first; denied or failed recall does not
reuse cached content. Recall is labeled as untrusted data and retains provenance,
space and version fields. It is not appended to the host transcript. No Skill
instruction or explicit user memory-tool call is needed to trigger these hooks.

The two local acceptance levels are deliberately distinct:

```sh
node --test tests/test_pi_owner_extension.mjs tests/test_pi_owner_host.mjs
QDRANT_OWNER_RUNTIME_ROOT=/path/to/runtime PYTHONPATH=/path/to/hermes-agent \
  /path/to/runtime/.venv/bin/python -m pytest tests/test_native_pi_handoff.py -q
```

The first uses the actual Pi session plus a fixture Owner call boundary. The
second invokes actual Hermes MemoryManager callbacks, one Native Runtime/Owner,
verified HTTPS MCP and a separate Pi process with a fresh session. Both use
deterministic model and embedding fixtures; neither proves production extraction
accuracy. The separate Runtime two-container suite proves TLS/network separation.

Pi 1.1.0 resolved incompatible 1.2.0 subpackages and failed to import; the test
manifest now pins Pi 1.3.0, which pins a consistent family of dependencies. The
lockfile records that tested set. Codex, DSH, WorkBuddy and OpenCode remain
explicit MCP/assisted modes until their own official lifecycle adapters are
implemented and verified; this Pi extension is not evidence for those hosts.

The Owner source preview supports device-bound event status/cancellation through
`remote-event --action status|cancel`. Cancellation is permitted only before any
extraction/write plan is prepared. Pi records `CANCELLED` as a distinct terminal
outbox acknowledgement and stops replaying it; it does not claim the event was
committed. Operator recovery gates remain in force after extraction failures.
