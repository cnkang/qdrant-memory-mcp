# Desktop-only submission preparation checklist

**Current status: NOT SUBMISSION READY.** This checklist is preparation only.

## Eligibility and publisher

- [ ] Confirm the publisher's verified identity and monitored security contact.
- [ ] Separately request and receive local-MCP Desktop-only allowlisting.
- [ ] Confirm current supported Desktop hosts and eligible OS/architecture
      matrix from OpenAI; do not infer from CLI or Linux CI.
- [ ] Publish real privacy, support and (if applicable) terms pages. Replace
      every DRAFT field with an actual reachable URL.

## Engineering package

- [ ] Build the separate `build-desktop-only-plugin` target from a clean,
      recorded commit. Preserve the source Marketplace target.
- [ ] Include each supported Python interpreter, MCP/Runtime distribution,
      dependency wheels and required platform binaries in the ZIP.
- [ ] Obtain confirmation that downloading model weights separately satisfies
      the requirement to include the server and its dependencies. Until this is
      confirmed, leave this item incomplete and the Desktop package NO-GO.
      Preserve the confirmation and official-review context, exact file sizes
      and hashes, and evidence for atomic cache publication, offline reuse,
      interruption, timeout and low-disk behavior.
- [ ] Generate per-platform SBOM and license notices; include source commits,
      Python/Node versions, dependency hashes, model origin/hash, build
      environment, archive size and SHA-256 in the release manifest.
- [ ] Verify the final package passes every archive size and structure
      constraint before
      reporting Desktop package readiness: the compressed ZIP is 100 MB or
      less, every archive entry is 100 MiB or less, the total extracted
      archive is 512 MiB or less, and the archive contains at most 5,000
      entries.
- [ ] Run portable schema validation, Creator-normalized manifest compatibility,
      secret scan, hostile archive/path tests and MCP protocol tests.
- [ ] Test exact final ZIP on every confirmed Desktop platform. Perform setup,
      four-tool discovery, CRUD, restart, migration/export, upgrade/rollback,
      disable and uninstall without data loss.
- [x] Runtime #118's interpreter-selection fix is merged in PR #127 and its
      exact-SHA CI run [42159067998](https://github.com/cnkang/hermes-plugin-qdrant-memory/actions/runs/42159067998)
      passed. GitHub issue #118 remains open as a tracking record.
- [ ] Resolve or explicitly gate Runtime #115 with Windows worker/ledger/lease
      and interrupted-write evidence.
- [ ] Verify all five positive and three negative reviewer cases. Preserve logs
      or artifacts for each result; never mark skipped tests PASS.
- [ ] Record real Codex Desktop and ChatGPT Desktop evidence separately from
      Codex CLI and MCP SDK evidence. Record a real demo video or leave it
      NOT RECORDED.
- [ ] Reconfirm current `HANDOFF_PENDING != NATIVE_VERIFIED` behavior and
      portable JSON/Markdown readability after uninstall.

## Release boundary

- [ ] Keep Desktop-only candidate and GitHub Marketplace source package
      distinguishable.
Treat an engineering PR merge as separate from release approval.
- [ ] Do not create a release tag, publish to registries, upload a Creator
      archive or submit to the public directory until all release checks and
      required approvals are complete.
- [ ] Report `ENGINEERING_READY`, `DESKTOP_PACKAGE_READY`,
      `SUBMISSION_MATERIALS_READY`, `BLOCKED_BY_PLATFORM` and `NOT_VERIFIED`
      separately. Never report official approval before OpenAI grants it.
