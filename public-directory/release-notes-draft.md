# Release notes draft — Qdrant Memory for Codex 0.1.3

**Status: DRAFT for the existing source Marketplace candidate. This is not a
Desktop-only release and must not be used as a claim that a complete Desktop
archive exists.**

Qdrant Memory for Codex provides explicit scoped search, add, exact-ID update
and exact-ID delete through the existing Qdrant Memory Runtime. It includes
guided new-profile, existing-Qdrant, migration, backup/exit and troubleshooting
workflows. The source package pins MCP 0.3.1, Runtime 0.6.0 and Skill 0.4.1.

Users keep their Qdrant data and readable exports. There is no automatic session
capture. Codex memory import is read-only; an exported handoff remains
`HANDOFF_PENDING` until the user verifies adoption through Codex.

**Desktop-only package status:** not ready. Runtime/dependency bundles,
Creator-normalized manifest test, clean Desktop test, SBOM and platform matrix
are incomplete. Do not publish these notes as a Desktop release.
