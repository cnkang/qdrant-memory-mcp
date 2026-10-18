# GitHub checks and dependency maintenance

- Distribution CI builds metadata-only artifacts and verifies installed MCP
  protocol behavior on Linux, macOS and Windows (Python 3.11/3.14), independently
  with MCP Python SDK 1.x and 2.x. Publication also tests both SDK majors against
  wheel and sdist installations using the public Runtime release.
  All 12 OS/Python/SDK combinations are required checks on the protected branch.
- Cross-harness integration runs the official DSH client against a disposable
  profile, installs the packed Bundle through the real `dsh plugin` command,
  and runs the exact public `npx` launcher commands (cold handshake,
  preparation, CRUD, persistence) on Linux, macOS and Windows.
- Repository quality runs Ruff on release scripts/tests and actionlint on every
  workflow, including shell steps. actionlint's archive is SHA256 verified.
- CodeQL analyzes Python and GitHub Actions with `security-extended` queries
  on PRs, main pushes and every Monday. The paired init/analyze actions use the
  same immutable commit.
- Dependency review blocks PRs that introduce high or critical dependency
  vulnerabilities. It uses read-only access and does not post PR comments.
- Dependabot checks pip manifests and GitHub Actions each Monday at 09:00
  Asia/Singapore, grouping updates by ecosystem. Updates remain reviewed PRs.
  There is no automatic merge or publication.

Actions use immutable commit pins. Dependabot updates both occurrences of the
CodeQL action together. Repository Dependabot security updates, secret scanning
and push protection are enabled. No additional service token is required.

## DSH dependency security and update channels

The reproducible cross-harness gate pins official DSH packages at
`0.2.1-rc.2`. Its upstream MCP Client/Core resolve to `2.2.0`, fixing
[GHSA-6qxp-vccf-f47h](https://github.com/advisories/GHSA-6qxp-vccf-f47h). The lockfile regression test rejects affected SDK
versions, including nested copies. The alert closes only after the corrected
lockfile reaches the default branch and GitHub re-evaluates it. A feature
branch push alone does not close it. No transitive override is used.

The separate `DSH next compatibility` workflow resolves the three official
packages from `next` weekly, manually, and when relevant integration sources
change. It runs the same real client/CLI/Bundle acceptance, rejects skipped
results, rejects high or critical advisories, and retains the resolved
dependency tree, generated lockfile and audit report. It is a compatibility signal, separate from the exact-version release
gate. Promote a tested `next` version by explicitly updating all three pins and
the committed lockfile. Do not replace `npm ci` with floating installs in the
release gate. The npm `latest` tags are not synchronized across these packages.

The 2026-10-17 audit of `0.2.1-rc.2` still reports one unrelated moderate
advisory, [GHSA-px8p-9vwx-vf98](https://github.com/advisories/GHSA-px8p-9vwx-vf98),
through the upstream Office conversion dependency on `fflate` (eight affected
dependency nodes). No high/critical advisories remain in this npm tree.
These npm dependencies are development-only contract-test dependencies. They
are not installed by Python artifacts or shipped in the configuration-only Bundle. Follow
up with an upstream DSH update rather than `npm audit fix --force`.

The Runtime dependency is exact at `0.4.0`. Runtime updates must also adjust
compatibility expectations and the preparation fixture deliberately. A dependency-only PR cannot bypass the
distribution's metadata/protocol checks. This repository scans distribution
scripts and workflows. Runtime business-code scanning belongs to its upstream.

Publishing remains tag-only behind the existing protected environments and
explicit publication confirmation. Adding checks does not trigger a release.
