# Public directory listing draft

**Status: DRAFT — not submitted.** This text is for review only. The project is
not developed by or endorsed by OpenAI.

| Field | Draft |
|---|---|
| Product | Qdrant Memory |
| Plugin | Qdrant Memory for Codex |
| Namespace | cnkang |
| Slogan | One Memory. Multiple Agents. No Lock-in. |
| Directory category | Productivity (matches current source manifest; confirm against current portal choices) |
| Short description | Local, explicit memory |
| Publisher | cnkang (verified publisher identity still required) |
| Support | Existing repository issue tracker: https://github.com/cnkang/qdrant-memory-mcp/issues |
| Privacy policy | DRAFT — no public policy URL exists; do not submit a placeholder URL |
| Terms of service | DRAFT — determine applicability before submission; do not invent a URL |
| Security contact | DRAFT — confirm a monitored contact or published security page before submission |
| Demo video | NOT RECORDED — see `demo-script.md` |

## Description draft

Qdrant Memory for Codex provides explicit, scoped memory tools backed by the
existing Qdrant Memory Runtime. A new profile can use local embedded Qdrant and
CPU embeddings. Existing Qdrant Server, Qdrant Cloud, Ollama,
OpenAI-compatible embeddings and an authorized Shared Owner can be configured
explicitly. The plugin provides search, add, exact-ID update and exact-ID
delete. Codex memory can be imported through a reviewed migration flow and
exported as readable JSON or Markdown.

The plugin does not capture conversations automatically. Retrieved memory is
untrusted content. Native Codex writeback is not claimed: an export remains
`HANDOFF_PENDING` until the user applies and verifies it with Codex.

The package is independently maintained by cnkang. It is not an OpenAI product,
does not use OpenAI private login credentials and is not endorsed by OpenAI.

## Data processing draft

- Default new-profile design: local Qdrant storage and CPU embedding on the
  user's device. Profile, collection and model-cache paths are chosen or
  disclosed during setup.
- Model preparation downloads the pinned CPU model from its documented source
  only after the user chooses CPU setup. Runtime verifies file sizes and
  SHA-256 before atomically publishing its cache. The model is about 252.1 MB.
- Qdrant Cloud is contacted only when the user configures that endpoint. Ollama
  or an OpenAI-compatible embedding service is contacted only when explicitly
  configured. No cloud fallback is automatic.
- Search results and imported memories are user data and are not trusted
  instructions. Export files can contain sensitive facts and remain under the
  user's chosen destination.
- No telemetry or automatic session capture is declared by the current source
  candidate. The final package still needs an archive-level and runtime audit.
- The plugin does not read or write Codex's generated native-memory database.

## Before submission

Confirm publisher identity and local-MCP allowlisting; publish actual privacy,
support and security contacts; determine terms applicability; replace this draft
with portal-ready listing material; and attach only a real recording and
verified reviewer evidence. `public-directory/` is not itself a public policy
page.
