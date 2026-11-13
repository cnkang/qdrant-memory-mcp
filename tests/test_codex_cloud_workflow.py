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
    """Require cloud acceptance to target the reviewed repository main commit."""
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
    assert cloud.count("uses: actions/checkout@") == 2
    assert "repository: cnkang/skills" in cloud
    assert "ref: ${{ steps.skill.outputs.commit }}" in cloud
    assert "scripts/build_codex_plugin.py" in cloud
    source_step = cloud.split(
        "      - name: Test repository-backed marketplace with protected Ollama\n",
        1,
    )[1].split("      - name:", 1)[0]
    zip_step = cloud.split(
        "      - name: Test exact rebuilt plugin ZIP with protected Ollama\n", 1
    )[1].split("      - name:", 1)[0]
    assert "--mode cloud" in source_step
    assert "--plugin-zip" not in source_step
    assert "codex-plugin-source-result.json" in source_step
    assert "continue-on-error: true" in source_step
    assert "--plugin-zip \"$CODEX_PLUGIN_ZIP\"" in zip_step
    assert "codex-plugin-zip-result.json" in zip_step
    assert "continue-on-error: true" in zip_step
    assert "codex-plugin-verified-source-${{ github.sha }}" in cloud
    assert "repository_marketplace_acceptance" in cloud
    assert "zip_acceptance" in cloud
    assert "archive_matches_build_metadata" in cloud
    assert "Both repository marketplace and exact ZIP acceptance must pass" in cloud
    assert "    timeout-minutes: 40\n" in cloud
    assert "github.event.inputs" not in text
    assert text.count("${{ secrets.SOAK_LLM_API_KEY }}") == 2
    assert "--mode cloud" in cloud
    assert "-m pip install" in cloud
    assert "--index-url https://pypi.org/simple" in cloud
    assert "-r plugins/qdrant-memory/requirements.txt" in cloud
    assert 'distribution.version != version' in cloud
    assert 'distribution.read_text("direct_url.json") is not None' in cloud
    assert 'source["vcs_info"]["commit_id"]' not in cloud
    assert "--force-reinstall" not in cloud


@pytest.mark.parametrize(
    "source_raw,zip_raw,build_raw,expected",
    [
        (None, None, None, "NOT VERIFIED"),
        (b"", b"{}", b"{}", "NOT VERIFIED"),
        (b"{", b"{}", b"{}", "NOT VERIFIED"),
        (b"\xff", b"{}", b"{}", "NOT VERIFIED"),
        (b"[]", b"{}", b"{}", "NOT VERIFIED"),
        (
            b'{"status":"PASS","installation_source":"repository"}',
            b'{"status":"PASS","installation_source":"zip","plugin_archive_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            b'{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            "PASS",
        ),
        (
            b'{"status":"FAIL","installation_source":"repository"}',
            b'{"status":"PASS","installation_source":"zip","plugin_archive_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            b'{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            "FAIL",
        ),
        (
            b'{"status":"PASS","installation_source":"repository"}',
            b'{"status":"PASS","installation_source":"zip","plugin_archive_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
            b'{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            "FAIL",
        ),
        (
            b'{"status":"PASS","installation_source":"repository"}',
            b'{"status":"FAIL","installation_source":"zip"}',
            b'{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            "FAIL",
        ),
    ],
)
def test_cloud_summary_requires_both_install_paths_and_matching_archive(
    tmp_path, source_raw, zip_raw, build_raw, expected
):
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text.split("      - name: Summarize explicit outcome\n", 1)[1].split(
        "      - uses:", 1
    )[0]
    assert "        if: always()\n" in step
    assert "        shell: python\n" in step
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    result_path = tmp_path / "codex-plugin-result.json"
    for name, raw in (
        ("codex-plugin-source-result.json", source_raw),
        ("codex-plugin-zip-result.json", zip_raw),
        ("codex-plugin-build.json", build_raw),
    ):
        if raw is not None:
            (tmp_path / name).write_bytes(raw)
    summary = tmp_path / "summary.md"
    summary.write_text("Previous summary\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_SHA": "a" * 40,
        },
        capture_output=True,
    )
    assert (result.returncode == 0) is (expected == "PASS"), result.stderr
    artifact = json.loads(result_path.read_text(encoding="utf-8"))
    assert artifact["status"] == expected
    if expected == "PASS":
        assert artifact["archive_matches_build_metadata"]
        assert artifact["repository_marketplace_acceptance"]["status"] == "PASS"
        assert artifact["zip_acceptance"]["installation_source"] == "zip"
    rendered = summary.read_text(encoding="utf-8")
    assert rendered.startswith("Previous summary\n")
    assert json.dumps(artifact, indent=2) in rendered
    assert "if-no-files-found: error" in text
