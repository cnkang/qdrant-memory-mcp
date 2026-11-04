"""Protected cloud credentials must never reach unreviewed client code."""

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
    assert "github.event.inputs" not in text
    assert text.count("${{ secrets.SOAK_LLM_API_KEY }}") == 1
    assert "--mode cloud" in cloud
    assert "-m pip install -r plugins/qdrant-memory/requirements.txt" in cloud
    assert 'source["vcs_info"]["commit_id"] == expected' in cloud
    assert "--force-reinstall" not in cloud
