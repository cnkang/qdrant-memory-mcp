"""Assert the credential-free security jobs and the zizmor scope."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def _workflow(name):
    """Load one workflow document with the trigger parsed as a string."""
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if "on" not in document and True in document:
        document["on"] = document.pop(True)
    return document


def test_quality_lint_carries_the_free_security_checks():
    """The required lint job must also run zizmor and gitleaks."""
    job = _workflow("quality.yml")["jobs"]["lint"]
    assert job["name"] == "Python and workflow lint"
    checkout = job["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0

    zizmor = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("zizmorcore/zizmor-action@")
    )
    assert len(zizmor["uses"].split("@")[1]) == 40
    assert zizmor["with"]["version"] == "1.32.0"
    assert zizmor["with"]["online-audits"] is False

    secret = str(job)
    assert "gitleaks_8.30.1_linux_x64.tar.gz" in secret
    assert "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb" in secret
    assert "--redact" in secret


def test_dependency_review_fails_closed_on_severity_and_license():
    """High advisories and strong copyleft licenses block a pull request."""
    step = next(
        step
        for step in _workflow("dependency-review.yml")["jobs"]["review"]["steps"]
        if step.get("uses", "").startswith("actions/dependency-review-action@")
    )
    assert len(step["uses"].split("@")[1]) == 40
    assert step["with"]["fail-on-severity"] == "high"
    assert "AGPL-3.0" in step["with"]["deny-licenses"]
    assert step["with"]["comment-summary-in-pr"] == "never"


def test_scorecard_never_gates_a_pull_request():
    """Scorecard publishes with OIDC on trusted events only."""
    workflow = _workflow("scorecard.yml")
    assert set(workflow["on"]) == {"push", "schedule", "workflow_dispatch"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["jobs"]["analysis"]["permissions"]["id-token"] == "write"


def test_credential_free_jobs_hold_no_secret():
    """Jobs that run on untrusted pull requests must not read secrets."""
    lint = _workflow("quality.yml")["jobs"]["lint"]
    review = _workflow("dependency-review.yml")["jobs"]["review"]
    for job in (lint, review):
        document = repr(job)
        assert "secrets." not in document
        assert "SNYK_TOKEN" not in document
        assert "SONAR_TOKEN" not in document


def test_zizmor_config_is_scoped_to_reviewed_files():
    """Exceptions must name files; a whole rule must never be disabled."""
    config = yaml.safe_load((ROOT / ".github/zizmor.yml").read_text(encoding="utf-8"))
    for rule, settings in config["rules"].items():
        assert "disable" not in settings, rule
        for entry in settings.get("ignore", []):
            assert re.fullmatch(r"[A-Za-z0-9._-]+\.yml", entry), entry
