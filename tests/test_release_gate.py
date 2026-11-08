"""Verify the release gate against simulated workflow-run metadata."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_release_gate import REQUIRED_WORKFLOWS, check_release_gate, main  # noqa: E402

WORKFLOWS = ROOT / ".github/workflows"
SHA = "b" * 40


def _workflow(name):
    """Load one workflow document with the trigger parsed as a string."""
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if "on" not in document and True in document:
        document["on"] = document.pop(True)
    return document


def _run(
    name,
    *,
    conclusion="success",
    event="push",
    branch="main",
    sha=SHA,
    status="completed",
):
    """Build one workflow-run record."""
    return {
        "id": abs(hash((name, conclusion, event, sha))) % 100000,
        "name": name,
        "head_sha": sha,
        "event": event,
        "head_branch": branch,
        "status": status,
        "conclusion": conclusion,
        "html_url": "https://example.invalid/run",
    }


def _fetch(runs):
    """Return a fetch callable with a fixed result set."""

    def fetch(repository, sha):
        """Ignore the query and return the prepared runs."""
        assert re.fullmatch(r"[0-9a-f]{40}", sha)
        return runs

    return fetch


def test_fetch_runs_reads_all_api_pages(monkeypatch):
    """Runs on later API pages must also count as release evidence."""
    from check_release_gate import _fetch_runs

    first = _run(REQUIRED_WORKFLOWS[0])
    second = _run(REQUIRED_WORKFLOWS[1])
    response = json.dumps([{"workflow_runs": [first]}, {"workflow_runs": [second]}])
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=response, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _fetch_runs("cnkang/qdrant-memory-mcp", SHA) == [first, second]
    assert "--paginate" in calls[0]
    assert "--slurp" in calls[0]
    assert f"head_sha={SHA}&per_page=100" in calls[0][-1]


def test_required_workflows_exist_and_run_on_main_push():
    """Every release-gate name resolves to a workflow with a main push trigger."""
    documents = {}
    for path in WORKFLOWS.glob("*.yml"):
        document = _workflow(path.name)
        if document.get("name"):
            documents[document["name"]] = document
    for name in REQUIRED_WORKFLOWS:
        assert name in documents, f"missing workflow: {name}"
        trigger = documents[name]["on"]
        assert "push" in trigger, f"{name} has no push trigger"
        assert "main" in (trigger["push"].get("branches") or []), f"{name} does not run on main"


def test_dsh_native_push_trigger_has_no_path_filter():
    """The release gate needs a run for every main commit, not only DSH edits."""
    workflow = _workflow("dsh-native.yml")
    assert "paths" not in workflow["on"].get("push", {})


def test_release_gate_passes_for_verified_commit():
    """Every required workflow passed on main for this exact commit."""
    runs = [_run(name) for name in REQUIRED_WORKFLOWS]
    report = check_release_gate("cnkang/qdrant-memory-mcp", SHA, fetch=_fetch(runs))
    assert report["passed"] is True
    assert set(report["workflows"]) == set(REQUIRED_WORKFLOWS)


@pytest.mark.parametrize("name", REQUIRED_WORKFLOWS)
@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "neutral", "skipped"])
def test_release_gate_rejects_any_failed_required_workflow(name, conclusion):
    """A failed, cancelled or skipped workflow blocks the release."""
    runs = [_run(item) for item in REQUIRED_WORKFLOWS if item != name]
    runs.append(_run(name, conclusion=conclusion))
    report = check_release_gate("cnkang/qdrant-memory-mcp", SHA, fetch=_fetch(runs))
    assert report["passed"] is False
    assert report["workflows"][name]["status"] == "failed"


def test_release_gate_rejects_missing_workflow():
    """A workflow that never ran for the commit blocks the release."""
    runs = [_run(name) for name in REQUIRED_WORKFLOWS[1:]]
    report = check_release_gate("cnkang/qdrant-memory-mcp", SHA, fetch=_fetch(runs))
    assert report["passed"] is False
    assert report["workflows"][REQUIRED_WORKFLOWS[0]]["status"] == "missing"


def test_release_gate_rejects_incomplete_workflow():
    """A still-running workflow blocks the release."""
    runs = [_run(name) for name in REQUIRED_WORKFLOWS[1:]]
    runs.append(_run(REQUIRED_WORKFLOWS[0], conclusion=None, status="in_progress"))
    report = check_release_gate("cnkang/qdrant-memory-mcp", SHA, fetch=_fetch(runs))
    assert report["passed"] is False
    assert report["workflows"][REQUIRED_WORKFLOWS[0]]["status"] == "incomplete"


def test_release_gate_ignores_other_shas_branches_and_events():
    """Ancestry alone is not evidence: the run must match the tagged commit."""
    runs = (
        [_run(name, sha="c" * 40) for name in REQUIRED_WORKFLOWS]
        + [  # a different commit with green CI
            _run(name, branch="feature") for name in REQUIRED_WORKFLOWS
        ]
        + [  # a pull request run for this commit
            _run(name, event="pull_request", branch=None) for name in REQUIRED_WORKFLOWS
        ]
    )
    report = check_release_gate("cnkang/qdrant-memory-mcp", SHA, fetch=_fetch(runs))
    assert report["passed"] is False
    assert all(entry["status"] == "missing" for entry in report["workflows"].values())


def test_release_gate_rejects_short_sha():
    """A short revision cannot identify a workflow run."""
    with pytest.raises(ValueError):
        check_release_gate("cnkang/qdrant-memory-mcp", SHA[:12], fetch=_fetch([]))


def test_main_reports_the_decision(monkeypatch, capsys):
    """The tag workflow calls main(), so both exit paths need coverage."""
    monkeypatch.setenv("GITHUB_REPOSITORY", "cnkang/qdrant-memory-mcp")
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setattr(
        "check_release_gate._fetch_runs",
        lambda repository, sha: [_run(name) for name in REQUIRED_WORKFLOWS],
    )
    assert main([]) == 0
    assert '"passed": true' in capsys.readouterr().out

    monkeypatch.setattr("check_release_gate._fetch_runs", lambda repository, sha: [])
    assert main([]) == 1
    captured = capsys.readouterr()
    assert '"passed": false' in captured.out
    assert "Release gate failed" in captured.err


def test_publish_runs_the_gate_before_building():
    """The tag workflow must verify CI evidence before producing artifacts."""
    build = _workflow("publish.yml")["jobs"]["build"]
    commands = [step.get("run", "") for step in build["steps"]]
    gate_index = next(
        index
        for index, command in enumerate(commands)
        if "check_release_gate.py" in command
    )
    build_index = next(
        index for index, command in enumerate(commands) if "python -m build" in command
    )
    assert gate_index < build_index
    assert build["permissions"]["actions"] == "read"
    assert build["permissions"]["attestations"] == "write"
    attestation = next(
        step
        for step in build["steps"]
        if step.get("uses", "").startswith("actions/attest-build-provenance@")
    )
    assert len(attestation["uses"].split("@")[1]) == 40
    assert attestation["with"]["subject-path"] == "dist/*"
    assert attestation["if"] == "steps.existing.outputs.exists != 'true'"


def test_release_workflows_do_not_read_caches():
    """A cached toolchain could be poisoned by a lower-privilege run."""
    setup_go = next(
        step
        for step in _workflow("publish.yml")["jobs"]["registry"]["steps"]
        if step.get("uses", "").startswith("actions/setup-go@")
    )
    assert setup_go["with"]["cache"] is False
    setup_node = next(
        step
        for step in _workflow("dsh-bundle-release.yml")["jobs"]["build"]["steps"]
        if step.get("uses", "").startswith("actions/setup-node@")
    )
    assert setup_node["with"]["package-manager-cache"] is False


def test_manual_release_dispatch_requires_a_matching_tag():
    """Manual dispatches from branches must skip privileged release jobs."""
    release_workflows = {
        "publish.yml": (
            "startsWith(github.ref, 'refs/tags/v')",
            {"pypi": "build", "registry": ["build", "pypi"]},
        ),
        "workbuddy-release.yml": (
            "startsWith(github.ref, 'refs/tags/v')",
            {"attach": "build"},
        ),
        "dsh-bundle-release.yml": (
            "startsWith(github.ref, 'refs/tags/dsh-bundle-v')",
            {"attach": "build"},
        ),
    }
    for filename, (expected_tag_guard, downstream_needs) in release_workflows.items():
        workflow = _workflow(filename)
        assert "workflow_dispatch" in workflow["on"]
        assert workflow["jobs"]["build"]["if"] == expected_tag_guard
        for job, needs in downstream_needs.items():
            assert workflow["jobs"][job]["needs"] == needs
