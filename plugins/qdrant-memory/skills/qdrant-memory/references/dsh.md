# DeepSeek Harness

Use the shared MCP server through DSH's official `@deepseek-ai/dsh-mcp-client`.
Follow the [English installation guide](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-integration.md)
or [中文说明](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-integration.zh-CN.md).
Loading this Skill does not authorize installing software or modifying a profile.

## Native lifecycle adapter status

The published Bundle and Python/uvx overlay remain explicit MCP paths. They do
not automatically capture or prefetch turns. The separate source-only native
Cordis adapter is an unpublished preview for DSH `0.2.2-rc.1` and Node.js
`>=24.9.0`; it requires a companion Python Runtime supporting the versioned
`qdrant-memory/extraction-v1` candidate event. That Runtime contract is not
available in the currently published Runtime packages, so do not present the
native adapter as a supported install yet.

The preview keeps `auto_recall.enabled`, `auto_capture.enabled`, and
`memory_injection.enabled` false by default. Recall needs both recall and
injection enabled; capture is independent. It asks DSH's current model route to
extract candidates and sends those candidates, not the raw assistant transcript,
to the authenticated Python Owner. DSH's configured model still receives the
turn content for extraction. Use a distinct Owner token for each unrelated DSH
profile. On a shared Owner, bind each unrelated profile to a distinct logical
agent and private space.
Runtime remains responsible for scope, relation review, deduplication,
durable receipts and Qdrant writes. No automatic sharing between DSH, Hermes,
or WorkBuddy private profiles is implied.

For preview configuration, profile-local migration and rollback, compatibility
and validation evidence, read the [native setup guide](https://github.com/cnkang/qdrant-memory-mcp/blob/cf51170b79b31d780f5227913ae3f1092ad0e8d9/integrations/dsh/native/README.md)
and [validation report](https://github.com/cnkang/qdrant-memory-mcp/blob/cf51170b79b31d780f5227913ae3f1092ad0e8d9/docs/dsh-native/validation.md).
The synthetic tests and profile install smoke do not establish real-model,
AgentLoop, Qdrant/CPU embedding, or desktop GUI acceptance.

Install this canonical `qdrant-memory` directory under a standard DSH Skill
root, such as `.agents/skills` in the selected project. DSH discovers
`qdrant-memory/SKILL.md` under that root. Keep its `references` and `scripts`
together. DSH's filesystem provider also
supports custom Skill roots. Point it at the directory that contains
`qdrant-memory`, not at `SKILL.md`. Do not maintain an independently edited copy.

Choose a DSH memory profile. A dedicated profile is recommended. Authorized
agents can also share one profile when they connect one at a time, under the
[shared memory](shared-memory.md) rules. Prepare the backend before you enable
the MCP overlay. DSH can start and close a temporary probe process before it
starts the persistent connection. Never put downloads or initialization in that
probe.
Apply the additional overlay with `dsh web --patch /absolute/path/to/overlay`.
Do not overwrite `cordis.patch.yml` or modify the default Profile. Enable only
one Qdrant Memory overlay per profile. DSH can also install the
configuration-only Bundle through its official Plugin Manager. The Bundle
declares the same MCP entry for one profile. Follow the
[installation guide](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-integration.md)
for the exact Bundle command and the current status. Do not install both
routes in one profile.

With server name `qdrant-memory`, discover:

| Tool | Operation |
| --- | --- |
| `mcp__qdrant-memory__qdrant_memory_search` | Scoped recall |
| `mcp__qdrant-memory__qdrant_memory_add` | Authorized explicit save |
| `mcp__qdrant-memory__qdrant_memory_update` | Authorized exact-ID replacement |
| `mcp__qdrant-memory__qdrant_memory_delete` | Authorized exact-ID deletion |

DSH scrubs credential-shaped variables from inherited stdio environments.
Explicitly forward required credential variables in the trusted MCP configuration
with `!!js process.env.VARIABLE`. Do not put secret values in YAML, arguments,
Skill text, transcripts or diagnostics. Respect DSH tool approval and cancellation.

A connected transport and four discovered tools do not establish backend
readiness. If preparation is pending or fails, report that no operation succeeded.
After an interruption, the outcome of a write can stay unknown. Do not repeat
an uncertain write unless a repeat is safe for that operation. To check the
result, compare the exact operation and its ID, not search ranking. For
acceptance, save a synthetic fact in one session. Retrieve and use it in a
fresh session without the old transcript. Then verify exact-ID update/delete
and full host restart persistence. Distinguish official client tests from
model/GUI acceptance. Neither implies automatic extraction or prefetch.

Use [maintenance](maintenance.md) through the standalone CLI when authorized.
Do not require Hermes CLI or WorkBuddy metadata. Never bypass WriterLease or open
the same embedded storage from two hosts. See [shared memory](shared-memory.md).
