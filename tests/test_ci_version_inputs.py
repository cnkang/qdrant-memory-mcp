"""Keep manual upstream-version probes bounded and reproducible."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_codex_cli_probe_accepts_only_exact_stable_versions():
    workflow = _workflow("codex-plugin.yml")
    version_input = workflow["on"]["workflow_dispatch"]["inputs"]["codex_cli_version"]
    assert version_input["default"] == "0.167.2"
    assert version_input["required"] == "false"
    assert version_input["type"] == "string"
    for job_name in ("portable", "lifecycle-e2e"):
        step = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if step.get("name") == "Install exact Codex CLI version"
        )
        assert (
            step["env"]["CODEX_CLI_VERSION"]
            == "${{ github.event.inputs.codex_cli_version || '0.167.2' }}"
        )
        assert "^[0-9]+\\.[0-9]+\\.[0-9]+$" in step["run"]
        assert "--ignore-scripts" in step["run"]
        assert "${CODEX_CLI_VERSION}" in step["run"]


def test_dsh_compatibility_probe_resolves_selected_host_into_its_lock():
    workflow = _workflow("dsh-next.yml")
    version_input = workflow["on"]["workflow_dispatch"]["inputs"]["dsh_version"]
    assert version_input["default"] == "next"
    assert version_input["required"] == "false"
    assert version_input["type"] == "string"
    step = next(
        step
        for step in workflow["jobs"]["next"]["steps"]
        if step.get("name")
        == "Resolve the selected official DSH packages into the runner lock"
    )
    assert (
        step["env"]["DSH_VERSION"] == "${{ github.event.inputs.dsh_version || 'next' }}"
    )
    assert "next|latest" in step["run"]
    assert "@deepseek-ai/dsh@${DSH_VERSION}" in step["run"]
    assert "@deepseek-ai/dsh-mcp-client@next" in step["run"]
    assert "@deepseek-ai/dsh-skill-filesystem@next" in step["run"]
    assert "npm install --package-lock-only" in step["run"]


def test_protected_cloud_acceptance_keeps_a_fixed_codex_cli_version():
    workflow = _workflow("codex-plugin-cloud.yml")
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["jobs"]["cloud"]["environment"] == "soak-cloud"
    install = next(
        step
        for step in workflow["jobs"]["cloud"]["steps"]
        if step.get("name") == "Install the declared Runtime and pinned Codex"
    )
    assert "@openai/codex@0.167.2" in install["run"]
