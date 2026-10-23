# 0.2.3 publication checklist

[English](publishing.md) | [简体中文](publishing.zh-CN.md)

No publishing tag or workflow dispatch is executed before the operator gives
explicit confirmation for the Runtime/PyPI/Registry publication.

Prepare versioned package/Registry metadata, README examples and release notes
in the release PR before building. `verify_metadata.py` requires the README's
install pin to match the distribution version, and PyPI artifacts are immutable.
An example identifies the intended release. It does not prove public availability.
Verify the exact public version before using its installation command. Announce
the release as available only after the checks below confirm both public endpoints.

1. Verify the existing public Runtime 0.4.0 release and exact dependency.
   Do not recreate its tag or publish it again for this distribution.
2. Recheck existing PyPI Trusted Publishers (PyPI account step):
   - `hermes-plugin-qdrant-memory`: owner `cnkang`, repository
     `hermes-plugin-qdrant-memory`, workflow `publish.yml`, environment `pypi`.
   - `qdrant-memory-mcp`: owner `cnkang`, repository `qdrant-memory-mcp`,
     workflow `publish.yml`, environment `pypi`.
3. Approve protected GitHub environments when prompted. A version tag must point
   to a main-branch commit and match package metadata. Releases cannot overwrite
   an existing version. Reuse the verified public Runtime 0.4.0 artifacts.
4. Run distribution acceptance in public dependency mode. Build/test wheel and
   sdist from a new environment using only the exact Runtime PyPI release.
5. Create distribution tag v0.2.3 after confirmation. Its workflow builds and
   tests before protected PyPI publication, verifies public metadata, validates
   with the official publisher, then uses `github-oidc` for Registry publication.
6. Verify PyPI ownership marker and the public Registry entry
   `io.github.cnkang/qdrant-memory` version 0.2.3. Publish the release announcement
   only after the public endpoints and public-install acceptance confirm the release.

The distribution workflow has a tag-only manual `registry_only` retry mode.
It downloads and verifies already-published PyPI artifacts and tests them,
then reruns Registry validation/publication. No PyPI upload occurs. Normal retries
also reuse a verified existing PyPI version. A mismatching package dependency,
entrypoint, ownership marker or Registry payload fails closed.

Publishing requires protected GitHub environments with required reviewers
and tag-only `v*` deployment policies: Runtime `pypi`, distribution `pypi`
and `mcp-registry`. Verify these controls before publication. Do not bypass them.
Both projects have published versions. Recheck the existing Trusted Publishers
and required reviewers. Do not create duplicate publishers.

## Adapter attachments for future versions

The [WorkBuddy adapter](../integrations/workbuddy/README.md) adds a separate
tag-triggered read-only build and Draft Release attachment job. The tag build
refuses to prepare assets while the pinned launcher version is not public on
the npm registry with matching integrity. Its ZIP and checksum record
independent Connector, MCP, Runtime, launcher-integrity and immutable Skill
versions.

The [DSH bundle](../integrations/dsh/bundle/README.md) has its own
`dsh-bundle-v*` tag flow in `dsh-bundle-release.yml`. It packs the
configuration-only bundle, verifies the payload against the reviewed source,
prepares the tarball checksum and attaches both files to a Draft Release.
Publishing the npm package `@cnkang/qdrant-memory-dsh-bundle` is a maintainer
step after a successful pack and test run.

Keep the existing protected PyPI/Registry environments, OIDC gates and public
acceptance unchanged. The adapter workflows do not upload PyPI or Registry
entries. No existing release is retrofitted. Wait for publication and adapter
preparation workflows before manually publishing the corresponding Draft.
Immutable releases require attachments before publication. Per-tag concurrency
serializes attachment runs, and existing publish.yml never writes Releases.

Reruns reuse matching bytes. Conflicting assets or a published release missing
assets fail closed. Preserve tags/assets and use a new approved release rather
than clobbering assets, moving tags or reuploading a PyPI version. Draft creation
and attachment preparation never replace the maintainer's publication decision.

The tag's WorkBuddy build tests the installed candidate, allowing Draft attachment
preparation before PyPI approval. It does not require an unpublished version to
already exist on PyPI. The protected publisher still requires public uvx
acceptance after publication. Preview requires public uvx when the exact version
is available. Otherwise it explicitly records that acceptance as NOT VERIFIED.

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
