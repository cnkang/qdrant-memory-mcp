# 0.1.1 patch publication checklist

No publishing tag or workflow dispatch is executed before the operator gives
explicit confirmation for the Runtime/PyPI/Registry publication.

1. Merge the Runtime release PR after all checks pass. Create Runtime tag v0.2.1
   on the merged commit, only after publication confirmation.
2. Configure PyPI Trusted Publishers (PyPI account step):
   - `hermes-plugin-qdrant-memory`: owner `cnkang`, repository
     `hermes-plugin-qdrant-memory`, workflow `publish.yml`, environment `pypi`.
   - `qdrant-memory-mcp`: owner `cnkang`, repository `qdrant-memory-mcp`,
     workflow `publish.yml`, environment `pypi`.
3. Approve protected GitHub environments when prompted. A version tag must point
   to a main-branch commit and match package metadata. Releases cannot overwrite
   an existing version. Publish Runtime 0.2.1 and verify its PyPI artifacts.
4. Run distribution acceptance in public dependency mode. Build/test wheel and
   sdist from a new environment using only the exact Runtime PyPI release.
5. Create distribution tag v0.1.1 after confirmation. Its workflow builds and
   tests before protected PyPI publication, verifies public metadata, validates
   with the official publisher, then uses `github-oidc` for Registry publication.
6. Verify PyPI ownership marker and the public Registry entry
   `io.github.cnkang/qdrant-memory` version 0.1.1. Remove candidate wording in
   documentation only when publication is confirmed by public endpoints.

The distribution workflow has a tag-only manual `registry_only` retry mode.
It downloads and verifies already-published PyPI artifacts and tests them,
then reruns Registry validation/publication. No PyPI upload occurs. Normal retries
also reuse a verified existing PyPI version. A mismatching package dependency,
entrypoint, ownership marker or Registry payload fails closed.

Publishing requires protected GitHub environments with required reviewers
and tag-only `v*` deployment policies: Runtime `pypi`, distribution `pypi`
and `mcp-registry`. Verify these controls before publication. Do not bypass them.
Both projects have published versions. Recheck the existing Trusted Publishers
and required reviewers before this patch. Do not create duplicate publishers.

Official references checked on 2026-10-13:

- [Publishing quickstart](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx)
- [Package types](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx)
- [server.json](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md)
- [Official requirements](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/official-registry-requirements.md)
- [GitHub Actions/OIDC](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/github-actions.mdx)

The current schema is 2025-12-11. PyPI ownership verification checks the package
description for `mcp-name: io.github.cnkang/qdrant-memory`. The CLI name matches
the PyPI identifier so uvx can run it directly. `mcp` remains a required positional
package argument and optional `--home` precedes it. Profile configuration carries
model/dimensions/scope, so environment declarations alone cannot initialize a
server. Secrets have no defaults or committed values.

Official publisher release v1.8.1 lists `validate` in help but reports
`Unknown command: validate`. Build the official CLI at fixed source commit
`11b7b0e274d518b6f449c5ee3518a6151d9848b9` instead. Do not accept the old
binary's misleading zero exit status as validation. The official validator uses
the Registry validation endpoint. Local vendored schema validation complements it.
