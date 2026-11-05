# CI free-tier policy

Every service used by this repository must have a written free-use basis, a
known trigger, and a defined failure mode. A service without all three is not a
merge gate.

Policy checked on 2026-11-05. Re-check the linked pages before adding a service
or changing a trigger.

## Services and free-use basis

| Service | Free basis | Metered? | Can a fork PR trigger it? |
| --- | --- | --- | --- |
| GitHub Actions (standard runners) | Free for public repositories | No billing for standard runners | Yes, but only credential-free jobs |
| GitHub CodeQL | Code scanning is free for public repositories | No | Yes |
| GitHub Dependency Review | Free for public repositories; needs the dependency graph | No | Yes |
| GitHub secret scanning and push protection | Free for public repositories | No | Push protection applies to every push |
| GitHub artifact attestations | Free for public repositories | No | No (tag only) |
| zizmor | Open source, runs offline, no account | No | Yes |
| actionlint | Open source, no account | No | Yes |
| gitleaks (CLI) | Open source, MIT, no account | No | Yes |
| OpenSSF Scorecard | Open source action; publishing uses the workflow's OIDC identity | No | No |
| SonarCloud | <https://www.sonarsource.com/plans-and-pricing/> lists SonarQube for OSS as free forever for public, OSI-licensed repositories with the paid Pro feature set | No | No (token held by the maintainer) |
| CodeRabbit | Open-source plan for public repositories | Partly: see below | It may comment, but it is not a gate |
| Sourcery | Free forever for public repositories | No for public repos | It may review, but it is not a gate |
| Socket | Free for open source | No for public repos | It may comment, but it is not a gate |

This repository does not use Snyk. It has no Snyk secret, no Snyk workflow step
and no Snyk project.

## SonarCloud

The documentation states that public OSI-licensed repositories get SonarQube for
OSS at no cost with the paid Pro feature set. This repository therefore keeps
one SonarCloud analysis per trusted event and never runs it on a fork.

Trigger policy:

| Job | Trigger | Calls per trigger |
| --- | --- | --- |
| `SonarCloud quality gate` | push to `main`/`codex/**`, same-repository PR, dispatch | one analysis |

A `codex/**` push and its open same-repository pull request use different
workflow refs, so both can analyze the same commit when neither run is
cancelled. That commit then consumes two SonarCloud analyses.

A fork pull request skips the job, and `ci.yml` does not aggregate it, so a
skipped analysis cannot be confused with a passing one. The quality gate is a
required check by name, so a fork pull request is covered by the other required
contexts instead.

Failure handling: a scanner error, an expired token or a failed quality gate
fails the job. `sonar.qualitygate.wait=true` means the scanner waits for the
verdict instead of returning early. There is no path that reports a missing
analysis as a pass.

## CodeRabbit

<https://docs.coderabbit.ai/management/plans> states that open-source projects
receive Team features with no paid subscription and that OSS review limits are
1–10 reviews per developer per hour, scoped per repository. Public repositories
with fewer than 10 stars require a manual trigger.

On-demand products are billed separately and require a payment method:
CodeRabbit Security Scan, CodeRabbit Agent, usage-based reviews and Deep Scan.
This repository enables none of them. Adding one would create an unmetered cost
path, so it is out of policy.

## Sourcery and Socket

<https://www.sourcery.ai/pricing> lists the Open Source plan as free forever for
public repositories, including security checks on every pull request.
<https://socket.dev/pricing> states that Socket is and will always be free for
open source. Neither is a required check; both are advisory reviewers.

## npm resolution probes

`dsh-next.yml` resolves `@deepseek-ai/dsh@next` weekly. It writes the resolution
into a runner-only lock and installs from that lock; nothing is committed. The
job has only the automatic read-only `GITHUB_TOKEN` (`contents: read`), and both
checkouts disable credential persistence. It has no publishing credential, so
an unwanted upstream release cannot publish or merge anything.

## What only the maintainer can verify

1. SonarCloud: confirm the project is bound to
   `https://github.com/cnkang/qdrant-memory-mcp`, that Automatic Analysis is
   off (it conflicts with CI analysis), and that the quality gate is unchanged.
2. CodeRabbit organisation: confirm usage-based reviews, Security Scan, Agent
   and Deep Scan are all disabled.
3. GitHub organisation billing: confirm no paid runner or metered product is
   attached to this repository.
4. Dependabot: confirm the seven-day cooldown appears in the dependency update
   configuration page.

## Review cadence

Re-check this document and the linked free-tier pages at each release and after
any change to a workflow trigger. A new trigger that adds a metered call needs a
row in the trigger table before it merges.
