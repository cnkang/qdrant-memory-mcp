# Qdrant Memory MCP Distribution Implementation Plan

**Goal:** Build, verify and push a metadata-only MCP distribution, then obtain the required first-publication confirmation.

**Architecture:** The console script references the upstream standalone entrypoint directly. Pin Runtime 0.2.0; prepare its release in a separate upstream PR because PyPI currently has no runtime release. Skills remain in cnkang/skills.

**Tech Stack:** setuptools, Python 3.11+, official MCP Python SDK, embedded Qdrant, GitHub Actions OIDC, official MCP publisher.

- [ ] Upstream: update pyproject.toml, version.py and both plugin manifests to 0.2.0; add release notes and gated Trusted Publishing. Run all tests and fresh-wheel standalone acceptance. Push codex/pypi-runtime-release and open PR.
- [ ] Distribution: add pyproject.toml with packages=[] and hermes-plugin-qdrant-memory[mcp]==0.2.0; add server.json using current 2025-12-11 schema and mcp positional argument. Verify wheel contains metadata only and README ownership marker survives build.
- [ ] Protocol acceptance: use a temporary profile, loopback deterministic HTTP embedding fixture and SDK stdio client. Exercise initialize, tools/list, all CRUD operations, restart, user/agent scope rejection, sanitized errors and stdout framing.
- [ ] CI: test installed wheel and sdist on Linux/macOS/Windows. Before Runtime PyPI release, bootstrap its exact reviewed commit into a local wheel; never place a Git dependency in published metadata. Release jobs must resolve Runtime from PyPI only.
- [ ] Release: tag-only publication through protected pypi and mcp-registry environments. Verify existing PyPI version metadata and artifact hashes before skipping uploads; allow Registry-only retry without repeating upload. Pin official publisher source if release binary lacks validate.
- [ ] Docs: English/Chinese usage, configuration, client examples, privacy and limitations; link upstream Runtime and Skill. Mark public installation pending until release.
- [ ] Delivery: create public repository, push code, wait for exact-SHA CI, save execution report and a concrete publication checklist. Do not push a publishing tag or dispatch publishing before explicit confirmation.
