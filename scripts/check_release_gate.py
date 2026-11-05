"""Refuse a tag release unless required workflows passed for the tagged commit."""

import json
import os
import re
import subprocess
import sys

# Workflows that must have produced a successful run for the exact commit that
# the tag points at. The list is intentionally limited to workflows that run on
# a push to main: a pull-request-only workflow cannot have a push run.
REQUIRED_WORKFLOWS = (
    "Distribution CI",
    "Cross-harness integration",
    "Repository quality",
    "CodeQL",
)


def _fetch_runs(repository, sha):
    """List workflow runs for the exact commit through the authenticated CLI."""
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/actions/runs?head_sha={sha}&per_page=100",
        ],
        capture_output=True,
        text=True,
    )
    result.check_returncode()
    return json.loads(result.stdout)["workflow_runs"]


def _select_main_push_runs(runs, sha):
    """Keep only completed-attempt candidates from a push to the main branch."""
    selected = {}
    for run in runs:
        if run.get("head_sha") != sha:
            continue
        if run.get("event") != "push" or run.get("head_branch") != "main":
            continue
        selected.setdefault(run.get("name"), []).append(run)
    return selected


def check_release_gate(repository, sha, fetch=None):
    """Return the per-workflow status and whether every required workflow passed."""
    if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
        raise ValueError("Release gate requires a full 40-character commit SHA")
    fetch = fetch or _fetch_runs
    selected = _select_main_push_runs(fetch(repository, sha), sha)
    results = {}
    for name in REQUIRED_WORKFLOWS:
        candidates = selected.get(name, [])
        successful = [
            run
            for run in candidates
            if run.get("status") == "completed" and run.get("conclusion") == "success"
        ]
        if successful:
            results[name] = {
                "status": "success",
                "run_id": successful[0].get("id"),
                "url": successful[0].get("html_url"),
            }
        elif any(run.get("status") != "completed" for run in candidates):
            results[name] = {"status": "incomplete", "run_id": None, "url": None}
        elif candidates:
            results[name] = {
                "status": "failed",
                "run_id": candidates[0].get("id"),
                "url": candidates[0].get("html_url"),
            }
        else:
            results[name] = {"status": "missing", "run_id": None, "url": None}
    return {
        "repository": repository,
        "sha": sha,
        "required": list(REQUIRED_WORKFLOWS),
        "workflows": results,
        "passed": all(entry["status"] == "success" for entry in results.values()),
    }


def main(argv=None):
    """Check the tagged commit and fail closed with a machine-readable report."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) >= 2:
        repository, sha = arguments[0], arguments[1]
    else:
        repository = os.environ["GITHUB_REPOSITORY"]
        sha = os.environ["GITHUB_SHA"]
    report = check_release_gate(repository, sha)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        print(
            "Release gate failed: every required workflow must pass for this commit.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
