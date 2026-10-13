# GitHub checks and dependency maintenance

- Distribution CI builds metadata-only artifacts and verifies installed MCP
  protocol behavior on Linux, macOS and Windows (Python 3.11/3.14).
- Repository quality runs Ruff on release scripts/tests and actionlint on every
  workflow, including shell steps. actionlint's archive is SHA256 verified.
- CodeQL analyzes Python and GitHub Actions with `security-extended` queries
  on PRs, main pushes and every Monday. The paired init/analyze actions use the
  same immutable commit.
- Dependency review blocks PRs that introduce high or critical dependency
  vulnerabilities. It uses read-only access and does not post PR comments.
- Dependabot checks pip manifests and GitHub Actions each Monday at 09:00
  Asia/Singapore, grouping updates by ecosystem. Updates remain reviewed PRs;
  there is no automatic merge or publication.

Actions use immutable commit pins. Dependabot updates both occurrences of the
CodeQL action together. Repository Dependabot security updates, secret scanning
and push protection are enabled; no additional service token is required.

The unpublished Runtime candidate remains the exact `0.2.0` dependency. Once
Runtime is on PyPI, its updates must also adjust compatibility expectations and
the preparation fixture deliberately; a dependency-only PR cannot bypass the
distribution's metadata/protocol checks. This repository scans distribution
scripts and workflows; Runtime business-code scanning belongs to its upstream.

Publishing remains tag-only behind the existing protected environments and
first-publication confirmation. Adding checks does not trigger a release.
