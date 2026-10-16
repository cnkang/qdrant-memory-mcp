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

## Accepted upstream advisory (test-only)

The DSH contract-test packages (`integrations/dsh/`) transitively pin
`@modelcontextprotocol/client@2.0.0` (required by
`@deepseek-ai/dsh-mcp-client@0.2.0-rc.2`), which a Dependabot alert flags
(GHSA-6qxp-vccf-f47h, OAuth credential disclosure, fixed in 2.2.0). This
dependency exists only in the test environment: it is not part of the
launcher, the connector package, the bundle or any release artifact, and the
release artifacts contain no JavaScript dependencies at all. The fix must
come from the upstream DSH line. When a DSH release resolves the client at
2.2.0 or newer, bump the devDependency here and refresh the lockfile. Until
then the alert stays open as a recorded, reviewed exception. Do not hand-edit
the lockfile to force a different transitive pin.

The Runtime dependency is exact at `0.3.0`. Runtime updates must also adjust
compatibility expectations and the preparation fixture deliberately. A dependency-only PR cannot bypass the
distribution's metadata/protocol checks. This repository scans distribution
scripts and workflows. Runtime business-code scanning belongs to its upstream.

Publishing remains tag-only behind the existing protected environments and
explicit publication confirmation. Adding checks does not trigger a release.
