# Third-party notices

This repository is MIT-licensed (see LICENSE). This file records third-party
components and the license assessment for the copyleft components that static
analyzers flag in the pinned lockfiles.

## Distributed artifacts

- The PyPI package `qdrant-memory-mcp` is metadata-only. It declares its
  dependency on the Qdrant Memory Runtime (MIT) but redistributes no
  third-party code.
- The WorkBuddy connector ZIP contains the canonical Qdrant Memory Skill
  (MIT, cnkang/skills) plus this repository's metadata and icon. It bundles
  no third-party code.
- The DSH integration directory ships configuration, documentation and
  lockfiles only.

## Development and CI dependencies (not distributed)

npm packages pinned for contract and acceptance testing. `node_modules` is
never committed and these packages are not part of any release artifact.

| Component | Version | License |
| --- | --- | --- |
| @deepseek-ai/dsh | 0.2.0-rc.2 | MIT |
| @deepseek-ai/dsh-mcp-client | 0.2.0-rc.2 | MIT |
| @deepseek-ai/dsh-skill-filesystem | 0.2.0-rc.2 | MIT |
| @opencode/cli | 2.0.24 | MIT |
| @earendil-works/pi-coding-agent | 1.1.0 | MIT |
| sharp | 0.35.5 | Apache-2.0 |
| @img/sharp-libvips-* (platform binaries) | 1.3.4 | LGPL-3.0-or-later |

`@img/sharp-libvips-*` are unmodified libvips binaries resolved as optional
dependencies of `sharp`. They run only in disposable test environments.
This project does not redistribute them, so the LGPL distribution
obligations (source offer, relinking) do not attach here. The
`@img/sharp-wasm32` and `@img/sharp-win32-*` variants declare
`Apache-2.0 AND LGPL-3.0-or-later`. The same assessment applies.

Python development and test dependencies are declared in `pyproject.toml`
and installed from PyPI at test time. They carry permissive licenses
(MIT, BSD, Apache-2.0).

## Components downloaded at runtime by the optional managed launcher (not redistributed)

The optional managed launcher downloads, verifies and executes these
components in a private program directory. This project does not
redistribute them.

| Component | Version / pin | License |
| --- | --- | --- |
| uv | 0.13.1 | Apache-2.0 OR MIT |
| Python (python-build-standalone) | 3.11.15 | PSF-2.0 |
| Qdrant Memory Runtime | pinned source archive revision | MIT |
| Embedding model `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q` | revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0` | Apache-2.0 (upstream model card) |

Model and archive downloads are size- and SHA-256-verified before use.
