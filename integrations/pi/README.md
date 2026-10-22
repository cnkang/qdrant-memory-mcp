# Pi Owner lifecycle adapter (source preview)

This adapter requires a reviewed Runtime source version with `remote-call` and `remote-event`.
Distribution packages continue to use Runtime 0.4.0.
This adapter is off by default. It uses Pi's public `session_start`,
`before_agent_start`, `context`, `turn_end` and `session_shutdown` extension hooks.
Tests use the actual Pi 1.3.0 session runtime and deterministic model responses.
These tests do not verify the user interface or production model quality.

Install `owner-memory.mjs` through Pi's extension configuration.
Configure the reviewed Runtime Python path and Owner endpoint.
Supply a separate credential through the host secret manager.
Set the configuration variables:

```sh
export QDRANT_MEMORY_RUNTIME_PYTHON=/path/to/reviewed-runtime/bin/python
export QDRANT_MEMORY_OWNER_URL=https://memory.example.com/mcp
export QDRANT_MEMORY_AUTO_RECALL=1
export QDRANT_MEMORY_AUTO_CAPTURE=1
```

The value must be an absolute path. The adapter runs that interpreter with `-I`
from its own directory and without `PYTHONPATH`, so host project content cannot
shadow the installed Runtime.

Supply `QDRANT_MEMORY_REMOTE_TOKEN` through the host secret environment.
Do not put the token in commands or repository files.
Use `QDRANT_MEMORY_CA_FILE` to trust a private certificate authority (CA).
Keep TLS verification enabled.
Do not put a Qdrant key on Pi.
Omit `QDRANT_MEMORY_AUTO_CAPTURE` for read-only clients.

A private credential captures private memory by default.
Shared or project capture also requires an approved Owner `capture_rule_id` for the intended project.
The extension cannot create this permission.
Event data cannot select another space.

For private capture with project recall, supply a separate read-only `QDRANT_MEMORY_RECALL_TOKEN`.
The adapter uses this token only for recall.
`QDRANT_MEMORY_REMOTE_TOKEN` binds capture and its durable outbox.
Each credential has an independent scope.
The administrator can revoke each credential separately.
Tool arguments cannot set the scope.

Enable the Owner `/events` lifecycle extension with an extraction model.
The adapter does not extract memories, create embeddings, or write a database.
It reads only permitted content from current hooks.
It does not read files or historical conversations.

Pi stores pending events through its official session API.
When the session resumes, the adapter retries these events with the same event IDs.
An outbox with 128 events stops new capture.
Restore the Owner connection before you continue capture.
Failed events remain in the current session outbox.
The adapter does not read pending events from other sessions.

The host controls deletion of local entries.
This operation does not delete Owner data.
An accepted, durable Owner event completes its recorded plan.
Use authorized memory tools to delete the resulting records.

The adapter requests recall through the ephemeral `context` hook before each model request.
It first removes earlier recall messages.
Failed or denied requests do not reuse cached content.
The adapter marks recalled content as untrusted data.
It retains provenance, space, and version fields.
It does not add recalled content to the host transcript.

These hooks do not require a Skill instruction or an explicit user call to a memory tool.

Run the extension and Pi session tests:

```sh
node --test tests/test_pi_owner_extension.mjs tests/test_pi_owner_host.mjs
```

Run the separate Hermes-to-Pi acceptance test:

```sh
QDRANT_OWNER_RUNTIME_ROOT=/path/to/runtime PYTHONPATH=/path/to/hermes-agent \
  /path/to/runtime/.venv/bin/python -m pytest tests/test_native_pi_handoff.py -q
```

The first command tests the extension and an actual Pi session with a simulated Owner response.
The second command invokes actual Hermes MemoryManager callbacks through one Native Owner Runtime and verified HTTPS MCP.
It uses a separate Pi process with a fresh session.
Both tests use deterministic model and embedding fixtures.
They do not verify production extraction accuracy.
The separate Runtime tests use two containers to verify TLS and network separation.

The test manifest and lockfile use Pi 1.3.0 with compatible dependencies.
Pi 1.1.0 selected incompatible 1.2.0 subpackages and could not import them.
Codex, DSH, WorkBuddy, and OpenCode support explicit MCP or assisted use.
They require separate, verified lifecycle adapters for automatic memory.
The Pi tests do not verify these other hosts.

The Owner source preview binds event status and cancellation to the device credential.
Use `remote-event --action status` to read event status.
Use `remote-event --action cancel` to request cancellation.
The Owner permits cancellation before it prepares an extraction or write plan.
Pi records `CANCELLED` as a terminal outbox acknowledgement and stops retries.
`CANCELLED` does not mean `COMMITTED`.

Extraction failures can require operator recovery.

See the [Owner capability summary](../../docs/universal-owner-status.md)
or its [Chinese translation](../../docs/universal-owner-status.zh-CN.md).
