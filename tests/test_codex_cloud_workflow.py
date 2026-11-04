"""Protected cloud credentials must never reach unreviewed client code."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/codex-plugin-cloud.yml"


@pytest.mark.parametrize(
    "event,ref,repo,accepted",
    [
        ("workflow_dispatch", "refs/heads/main", "cnkang/qdrant-memory-mcp", True),
        ("pull_request", "refs/heads/main", "cnkang/qdrant-memory-mcp", False),
        ("workflow_dispatch", "refs/heads/topic", "cnkang/qdrant-memory-mcp", False),
        ("workflow_dispatch", "refs/heads/main", "other/qdrant-memory-mcp", False),
    ],
)
def test_cloud_preflight_restricts_the_actual_checkout(
    tmp_path, event, ref, repo, accepted
):
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "on:\n  workflow_dispatch:\npermissions:\n  contents: read\n" in text
    preflight, cloud = text.split("  cloud:\n", 1)
    assert "        shell: python\n" in preflight
    script = textwrap.dedent(preflight.split("        run: |\n", 1)[1])
    output = tmp_path / "github-output"
    sha = "a" * 40
    env = {
        **os.environ,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_REPOSITORY": repo,
        "GITHUB_SHA": sha,
        "GITHUB_OUTPUT": str(output),
    }
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True
    )
    assert (result.returncode == 0) is accepted
    if accepted:
        assert output.read_text().strip() == "client_sha=" + sha
    else:
        assert not output.exists()
    assert "    needs: preflight\n" in cloud
    assert "    environment: soak-cloud\n" in cloud
    assert "ref: ${{ needs.preflight.outputs.client_sha }}" in cloud
    assert "persist-credentials: false" in cloud
    assert cloud.count("uses: actions/checkout@") == 1
    assert "continue-on-error:" not in cloud
    assert "github.event.inputs" not in text
    assert text.count("${{ secrets.SOAK_LLM_API_KEY }}") == 1
    assert "--mode cloud" in cloud
    assert "-m pip install -r plugins/qdrant-memory/requirements.txt" in cloud
    assert 'source["vcs_info"]["commit_id"] == expected' in cloud
    assert "--force-reinstall" not in cloud


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "NOT VERIFIED"),
        (b"", "NOT VERIFIED"),
        (b"{", "NOT VERIFIED"),
        (b"\xff", "NOT VERIFIED"),
        (b"[]", "NOT VERIFIED"),
        (b'{"status":"PASS","count":3}', "PASS"),
        (b'{"status":"FAIL","detail":"fixture"}', "FAIL"),
    ],
)
def test_cloud_summary_always_provides_an_explicit_artifact(tmp_path, raw, expected):
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text.split("      - name: Summarize explicit outcome\n", 1)[1].split(
        "      - uses:", 1
    )[0]
    assert "        if: always()\n" in step
    assert "        shell: python\n" in step
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    result_path = tmp_path / "codex-plugin-result.json"
    if raw is not None:
        result_path.write_bytes(raw)
    summary = tmp_path / "summary.md"
    summary.write_text("Previous summary\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    artifact = json.loads(result_path.read_text(encoding="utf-8"))
    assert artifact["status"] == expected
    if expected != "NOT VERIFIED":
        assert result_path.read_bytes() == raw
    rendered = summary.read_text(encoding="utf-8")
    assert rendered.startswith("Previous summary\n")
    assert json.dumps(artifact, indent=2) in rendered
    assert "if-no-files-found: error" in text
