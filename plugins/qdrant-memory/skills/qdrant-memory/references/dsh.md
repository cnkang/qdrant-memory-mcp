# DeepSeek Harness

Use the shared MCP server through DSH's official `@deepseek-ai/dsh-mcp-client`.
Follow the [English installation guide](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-integration.md)
or [中文说明](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-integration.zh-CN.md).
Loading this Skill does not authorize installing software or modifying a profile.

## Native lifecycle adapter status

The published Bundle and Python/uvx overlay remain explicit MCP paths. They do
not automatically capture or prefetch turns. The existing Bundle's
`0.2.0-rc.1` source candidate adds optional Native lifecycle under the same
`@cnkang/qdrant-memory-dsh-bundle` npm name. The private Native module remains
canonical source, not a second publication. The candidate requires DSH `0.2.2-rc.1` and Node.js
`>=24.9.0`; its extraction-v1 event prerequisite is available in published
Runtime 0.6.1. Runtime 0.6.2 is now public and adds explicit recovery for
persisted `FAILED` Owner events; the DSH adapter does not issue that operation
automatically. This clears a Runtime publication prerequisite only. The DSH
source candidate is not a published or release-ready install: its protected
Ollama Cloud matrix is not yet green, full UPDATE/CONFLICT and cross-client
acceptance is incomplete, and Desktop GUI acceptance remains unverified. The
currently published Bundle remains 0.1.6.

The candidate defaults to `mode: legacy`, preserving the existing four tools
without requiring an Owner token. It rejects automatic memory in Legacy mode.
`native-owner` selects only the HTTPS Owner lifecycle; `unified-owner` connects
the four tools and lifecycle to the same endpoint and token. Changing modes
never migrates existing profile data. Do not combine the Bundle with the old
overlay or the private Native package. Roll back to public Bundle 0.1.6 when
the Host or Node version cannot satisfy the candidate's explicit requirements.

One Owner-enabled DSH profile represents one trusted identity; a shared Host
does not authorize every person using it. First enabling Capture excludes
earlier history. Recovery may replay only turns after the durable activation
boundary, using stable Owner receipts; no implicit backfill is authorized.

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

For preview configuration, profile-local migration and rollback, read the
[candidate Bundle configuration guide](https://github.com/cnkang/qdrant-memory-mcp/blob/2ed833df84658837f3c31dfc6fc5e2d64a6f9401/integrations/dsh/bundle/README.md).
For compatibility and validation evidence, read [PR #81](https://github.com/cnkang/qdrant-memory-mcp/pull/81)
and its [release gap report](https://github.com/cnkang/qdrant-memory-mcp/blob/2ed833df84658837f3c31dfc6fc5e2d64a6f9401/docs/dsh-native/release-readiness.md).
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
published Legacy Bundle through its official Plugin Manager. The candidate
uses one Host entry to select one storage mode for the profile. Follow the
[installation guide](https://github.com/cnkang/qdrant-memory-mcp/blob/main/docs/dsh-integration.md)
for the exact Bundle command and the current status. Do not install both
routes in one profile.

The four-tool discovery and acceptance steps below apply to `legacy` and
`unified-owner`. `native-owner` opens no MCP connection and provides no MCP
tools; use `unified-owner` when you need explicit MCP tools alongside the
Native lifecycle.

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

For `legacy` and `unified-owner`, a connected transport and four discovered
tools do not establish backend readiness. If preparation is pending or fails,
report that no operation succeeded. These MCP checks do not apply to
`native-owner`, which has no MCP transport or tools.
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
