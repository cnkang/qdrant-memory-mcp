# CI security audit

Audit date: 2026-11-05. Scope: every workflow, the Dependabot configuration,
the branch protection rules and every third-party scanner used by this
repository.

## Method

- Read every file under `.github/` plus the release scripts that the tag
  workflow calls.
- Queried the GitHub API for branch protection, rulesets, environments, Actions
  permissions, secret names (never values), fork approval policy, artifact
  retention and 30 days of workflow runs.
- Ran actionlint 1.7.12, zizmor 1.32.0 and gitleaks 8.30.1 against the tree that
  CI uses.
- Replayed `scripts/check_release_gate.py` against simulated run lists.
- Checked the published free-tier terms for every third-party service; the
  citations are in [CI free-tier policy](ci-free-tier-policy.md).

## Workflow inventory

| Workflow | Trigger | Credential | Trust level |
| --- | --- | --- | --- |
| `ci.yml` | push `main`/`codex/**`, PR, dispatch | none | Tier 1 |
| `quality.yml` | push `main`/`codex/**`, PR, dispatch | `SONAR_TOKEN` in the SonarCloud job only | Tier 1 plus Tier 2 |
| `dependency-review.yml` | PR | none | Tier 1 |
| `codeql.yml` | push `main`, PR, weekly | `security-events: write` | Tier 1 |
| `cross-harness.yml` | push `main`/`codex/**`, PR, dispatch | none | Tier 2 |
| `codex-plugin.yml` | selected paths, PR, dispatch | none | Tier 2 |
| `managed-bootstrap.yml` | push, PR, dispatch | none | Tier 2 |
| `workbuddy-preview.yml` | push, PR, dispatch | none | Tier 2 |
| `dsh-next.yml` | weekly, selected paths, dispatch | `GITHUB_TOKEN` (`contents: read`) | Tier 3 |
| `codex-plugin-cloud.yml` | dispatch | environment | Tier 3 |
| `publish.yml` | tag `v*`, dispatch | build: OIDC and attestations (no environment); PyPI/Registry: OIDC behind protected environments | Tier 4 |
| `workbuddy-release.yml` | tag, dispatch | `contents: write` in attach job (no environment) | Tier 4 |
| `dsh-bundle-release.yml` | tag, dispatch | `contents: write` in attach job (no environment) | Tier 4 |
| `scorecard.yml` | push `main`, weekly, dispatch on `main` | read-only `GITHUB_TOKEN`; OIDC `id-token: write` | Tier 3 |

## Trust boundary analysis

**Fork pull requests.** They receive no repository secret, a read-only
`GITHUB_TOKEN` and no OIDC identity. The SonarCloud job skips any pull request
whose head repository differs from this one. No workflow uses
`pull_request_target`.

**Release workflows.** `publish.yml`, `workbuddy-release.yml` and
`dsh-bundle-release.yml` also support `workflow_dispatch`. Their build jobs
require a matching release tag (`refs/tags/v*` or
`refs/tags/dsh-bundle-v*`), so dispatching from a branch skips the build and
its dependent privileged jobs. None declares a `pull_request` trigger. The
`publish.yml` build job requests `id-token: write` and `attestations: write`
without an environment; it needs these permissions only to attest newly built
artifacts. Its PyPI and Registry publication jobs use OIDC behind the `pypi`
and `mcp-registry` environments. The WorkBuddy and DSH attachment jobs request
`contents: write` without a protected environment.

**Artifacts.** `distributions` crosses from build to the PyPI job, which
publishes it with OIDC when the PyPI version is new. Both jobs run from the same
tag. The build attests only files it built in that run; reused public PyPI bytes
are not attested as new build output. The release workflows never consume an
artifact produced by a pull request.

**Caches.** No release workflow reads a cache. `setup-go` in `publish.yml` and
`setup-node` in `dsh-bundle-release.yml` now disable caching explicitly, which
removes a cache-poisoning path from the publishing context.

**OIDC.** `publish.yml`'s build, PyPI and Registry jobs, and `scorecard.yml`
request `id-token: write`. The build job attests newly built artifacts; the
PyPI and Registry jobs publish behind protected environments. Scorecard's
`GITHUB_TOKEN` is read-only; `id-token: write` only enables the separate OIDC
identity used to publish the score.

**`workflow_run`.** No workflow uses it in this repository.

## Findings

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| F-01 | High | `publish.yml` verified only that the tag matched the version and that the commit was an ancestor of `main`. A commit whose required workflows failed could publish. | Fixed. `scripts/check_release_gate.py` requires a successful push-to-`main` run of `Distribution CI`, `Cross-harness integration`, `DSH native adapter`, `Repository quality` and `CodeQL` for the exact 40-character tagged SHA, before the build starts. |
| F-02 | Medium | Release jobs read the Actions cache through `setup-go` and `setup-node`. A lower-privilege run can write that cache. | Fixed. Caching is disabled in both release workflows. |
| F-03 | Medium | Distributions had no provenance statement outside PyPI Trusted Publishing. | Fixed. The build job attests only newly built `dist/*`; when it reuses public PyPI bytes it skips attestation. `attestations: write` is limited to that build job. |
| F-04 | Medium | Workflows were linted but not security-audited, and no job scanned incoming commits for secrets. | Fixed. The required `Python and workflow lint` job now also runs zizmor 1.32.0 and gitleaks 8.30.1, so both are covered by the existing branch protection without changing a required-check name. |
| F-05 | Low | Dependency review failed on severity only; a strong-copyleft dependency could merge. | Fixed. It now denies AGPL-3.0, GPL-2.0, GPL-3.0 and SSPL-1.0. |
| F-06 | Low | Dependabot adopted new releases immediately. | Fixed. Seven-day cooldown on both ecosystems. |
| F-07 | Low | zizmor reports five ad-hoc npm installs. | Accepted and scoped per file in `.github/zizmor.yml`: globally installed CLIs have no lockfile, each pin is exact, and the jobs hold no publishing credential. The `dsh-next` probe has only the automatic `GITHUB_TOKEN` with `contents: read`; both checkouts disable credential persistence. It resolves floating dist-tags into a runner-only lock by design. |
| F-08 | Medium | `main` requires 17 individual status contexts, including every matrix leg of `Distribution`. Renaming a matrix label silently blocks merges, and the `registry` context name exists in two workflows. | Open. Documented below with the recommended aggregate and the exact rollback. |
| F-09 | Accepted | `main` requires zero approving reviews. A solo maintainer cannot approve their own pull request. | Accepted with CODEOWNERS as the review prompt. |
| F-10 | Accepted | `gh api` release-gate reads need `actions: read`. | Least privilege for the read-only API call. |

## Repository settings

Verified through the API on 2026-11-05:

| Setting | MCP |
| --- | --- |
| Default workflow permissions | read |
| Workflow can approve pull requests | no |
| Secret scanning | enabled |
| Push protection | enabled |
| Dependabot security updates | enabled |
| Artifact and log retention | 90 days |
| Conversation resolution | required |
| Stale review dismissal | enabled |
| Required approving reviews | 0 |
| Force push / deletion | blocked |
| Release tag ruleset | immutable `v*` tags, active |
| Fork workflow approval | `all_external_contributors` |

## Run baseline (30 days)

| Workflow | Runs | Success | Cancelled | Failure | Median | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| Distribution CI | 100+ | 67% | 32% | 1% | 10 min | 29 min |
| Cross-harness integration | 100+ | 68% | 31% | 1% | 7 min | 22 min |
| Repository quality | 100+ | 71% | 20% | 9% | 5 min | 14 min |
| CodeQL | 100+ | 89% | 11% | 0% | 2 min | 14 min |
| Dependency review | 100+ | 90% | 9% | 1% | 1.5 min | 7 min |
| DSH next compatibility | 100+ | 88% | 4% | 8% | 2 min | 9 min |
| Managed Python prerequisite | 100+ | 79% | 20% | 1% | 3 min | 15 min |
| WorkBuddy connector preview | 100+ | 87% | 13% | 0% | 2 min | 8 min |
| Publish distribution | 16 | 94% | 0% | 6% | 8 min | 18 min |
| Prepare WorkBuddy assets | 12 | 100% | 0% | 0% | 2 min | 3 min |

The `DSH native adapter` workflow is new. It has no 30-day baseline yet and is
excluded from the percentages above until enough runs exist.

Cancellations track the `codex/**` dual lane (push plus pull request for the
same commit) and are deliberate. The push and pull request use different
`github.ref` concurrency groups, so both SonarCloud jobs may run when neither is
cancelled. This can produce two SonarCloud analyses for one commit; the other
duplicate work is the validation matrix.

## Verification

- `pytest tests/test_ci_security.py tests/test_release_gate.py`: 37 passed.
  Covers exact-SHA matching, wrong-SHA,
  wrong-branch, pull-request-only evidence, missing and incomplete runs, API
  pagination, gate ordering before `python -m build`, cache disabling, the new
  lint steps and the zizmor scope.
- actionlint 1.7.12 on the whole tree: clean.
- zizmor 1.32.0 offline: no findings with five file-scoped exceptions.
- gitleaks 8.30.1 over the full history: zero findings.

## Manual actions

1. Snyk is not used by this repository; there is nothing to confirm there.
   Fork workflow approval is already `all_external_contributors`; rollback is
   `-f approval_policy=first_time_contributors`.
2. Optional follow-up for F-08: add one aggregate job that needs both
   `distribution` and `registry`, then replace the 17 contexts with that job
   plus the four workflow-level names. Rollback is the current list, available
   from `gh api repos/cnkang/qdrant-memory-mcp/branches/main/protection`.

## Residual risks

- The release gate trusts GitHub's workflow-run list. A deleted run would make
  the tag look unverified and block the release, which fails closed.
- `registry` exists as a context name in both `ci.yml` (validation only) and
  `publish.yml` (publication). Pull request checks can only be satisfied by the
  validation job, so this is a UI ambiguity rather than a bypass; the follow-up
  aggregate would remove it.
- A tag on a commit that predates the gate runs that commit's `publish.yml`,
  which has no exact-SHA step. Such a tag is not gated. The check applies to
  commits that contain the step, which starts at `70249cf`.
- A tag on a gated commit can point at an older commit with green workflows.
  That is the intended semantic: the gate verifies the tagged commit, not the
  branch tip.
