# Public naming

The approved product name is **Qdrant Memory**. The Codex integration is
**Qdrant Memory for Codex**. The product describes the memory implementation;
the suffix describes the harness. The author remains identified separately.

| Surface | Name |
|---|---|
| Product | Qdrant Memory |
| Codex display name | Qdrant Memory for Codex |
| Portable plugin identifier | `qdrant-memory` |
| Repository Marketplace identifier | `cnkang` |
| Marketplace display name | Kang's plugins |
| Codex install selector | `qdrant-memory@cnkang` |
| Export/backup promise | One Memory. Multiple Agents. No Lock-in. |

The repository Marketplace uses the publisher namespace so future plugins can
share the same catalog. Its display name can evolve independently of the stable
`cnkang` identifier. The plugin retains its own product name throughout its
configuration, installation commands, tests and skills. No compatibility alias
is retained for the unpublished candidate namespace. Existing profiles,
collections, vector identities and data formats do not depend on that namespace.

The Runtime PyPI package, MCP distribution and MCP Registry identifier already
have public releases. Their existing identifiers remain intact; this change
renames the new Codex Marketplace, not those published distribution contracts.
