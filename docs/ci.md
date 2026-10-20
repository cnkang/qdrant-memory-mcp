# GitHub checks and dependency maintenance

Distribution CI tests the released Runtime version in fresh wheel and sdist environments.
It rejects skipped acceptance tests.
The separate `owner-lifecycle` job runs the Hermes-to-Pi source preview test.
This job installs fixed Runtime, Hermes, and Pi versions.
It also rejects skipped tests.
Distribution CI excludes this test because Runtime 0.4.0 does not provide the preview API.
An unavailable preview must not weaken distribution checks.

- Distribution CI builds metadata-only artifacts.
  It tests installed MCP behavior on Linux, macOS, and Windows.
  Tests cover Python 3.11 and 3.14 with MCP Python SDK 1.x and 2.x.
  Publication also tests both SDK versions against wheel and sdist installations with the public Runtime release.
  The protected branch requires all 12 operating system, Python, and SDK combinations.
- Cross-harness integration runs the official DSH client with a temporary profile.
  It installs the packed Bundle through the real `dsh plugin` command.
  It runs the exact public `npx` launcher commands on Linux, macOS, and Windows.
  Tests cover the initial handshake, preparation, memory operations, and persistence.
- Repository quality runs Ruff on release scripts and tests.
  It runs actionlint on every workflow, including shell steps.
  CI verifies the SHA256 digest of the actionlint archive.
- CodeQL analyzes Python and GitHub Actions with `security-extended` queries
  on PRs, main pushes and every Monday. The paired init/analyze actions use the
  same immutable commit.
- Dependency review blocks PRs that introduce high or critical dependency
  vulnerabilities. It uses read-only access and does not post PR comments.
- Dependabot checks pip manifests and GitHub Actions each Monday at 09:00
  Asia/Singapore, grouping updates by ecosystem. Updates remain reviewed PRs.
  There is no automatic merge or publication.

Actions use immutable commit pins. Dependabot updates both occurrences of the
CodeQL action together. The repository enables Dependabot security updates, secret scanning,
and push protection. These checks require no additional service token.

## DSH dependency security and update channels

The reproducible cross-harness gate pins official DSH packages at
`0.2.1-rc.2`. A temporary test-only override pins MCP Client to `2.3.0`, with Core `2.3.0`.
It fixes [cross-origin redirect leakage](https://github.com/advisories/GHSA-6prh-2h8m-c8cw).
The earlier [OAuth fix](https://github.com/advisories/GHSA-6qxp-vccf-f47h) remains included.
Remove the override after an upstream DSH update uses a fixed client, then rerun the actual client acceptance.
The lockfile test rejects affected versions, including nested copies.
The redirect advisory affects HTTP and OAuth. This repository's DSH acceptance uses unaffected stdio.
GitHub closes the alert only after the corrected lockfile reaches the default branch and is evaluated.
A feature branch push alone does not close it.

The separate `DSH next compatibility` workflow resolves the three official
packages from `next` weekly, manually, and when relevant integration sources
change. It runs the same real client/CLI/Bundle acceptance, rejects skipped
results, rejects high or critical advisories, and retains the resolved
dependency tree, generated lockfile and audit report. It is a compatibility signal, separate from the exact-version release
gate. Promote a tested `next` version by explicitly updating all three pins and
the committed lockfile. Do not replace `npm ci` with floating installs in the
release gate. The npm `latest` tags are not synchronized across these packages.
The `next` probe retains the test-only overrides. Inspect its resolved tree before removing an override.

A second test-only override selects `fflate 0.8.3` for `@deepseek-ai/libreoffice-kit`.
It fixes the [malformed ZIP64 parser advisory](https://github.com/advisories/GHSA-px8p-9vwx-vf98).
The three official DSH packages stay at `0.2.1-rc.2`.
Remove this override after an upstream Office dependency uses a fixed parser.
Then repeat the clean installation, audit, and actual DSH acceptance tests.
Do not use `npm audit fix --force`.

The clean installation and `npm audit` on 2026-10-20 (UTC) reported zero vulnerabilities.
The lockfile test rejects affected parser copies, including nested copies.
Acceptance tests resolve the parser through the Office package.
They verify a ZIP roundtrip and reject a malformed ZIP64 archive within a fixed timeout.
These npm dependencies serve development tests only.
Python artifacts and the configuration-only Bundle do not include them.

The Runtime dependency uses the exact version `0.4.0`.
For a Runtime update, also update compatibility expectations and the preparation fixture.
A dependency-only PR cannot bypass distribution metadata and protocol checks.
This repository scans distribution scripts and workflows.
The upstream Runtime repository scans Runtime business code.

Publication requires a tag, the existing protected environments, and explicit confirmation.
New checks do not trigger a release.
