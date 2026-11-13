"""Keep manual upstream-version probes bounded and reproducible."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_codex_cli_probe_accepts_only_hash_locked_stable_versions():
    workflow = _workflow("codex-plugin.yml")
    version_input = workflow["on"]["workflow_dispatch"]["inputs"]["codex_cli_version"]
    assert version_input["default"] == "0.167.2"
    assert version_input["required"] == "false"
    assert version_input["type"] == "choice"
    assert version_input["options"] == ["0.167.2", "0.165.0"]
    for version in version_input["options"]:
        lock_dir = ROOT / ".github" / "codex-cli-locks" / version
        manifest = json.loads((lock_dir / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((lock_dir / "package-lock.json").read_text(encoding="utf-8"))
        assert manifest["dependencies"]["@openai/codex"] == version
        assert lock["packages"]["node_modules/@openai/codex"]["version"] == version
        assert lock["packages"]["node_modules/@openai/codex"].get("integrity")
    for job_name in ("portable", "lifecycle-e2e"):
        step = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if step.get("name") == "Install hash-locked Codex CLI version"
        )
        assert (
            step["env"]["CODEX_CLI_VERSION"]
            == "${{ github.event.inputs.codex_cli_version || '0.167.2' }}"
        )
        assert "checked-in dependency lock" in step["run"]
        assert 'cd "$install_dir" && npm ci' in step["run"]
        assert "package-lock.json" in step["run"]
        assert "--ignore-scripts" in step["run"]
        assert "node_modules/.bin" in step["run"]


def test_dsh_compatibility_probe_resolves_selected_host_into_its_lock():
    workflow = _workflow("dsh-next.yml")
    version_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    step = next(
        step
        for step in workflow["jobs"]["next"]["steps"]
        if step.get("name")
        == "Resolve the selected official DSH packages into the runner lock"
    )

    for input_name, env_name in (
        ("dsh_version", "DSH_VERSION"),
        ("dsh_mcp_client_version", "DSH_MCP_CLIENT_VERSION"),
        ("dsh_skill_filesystem_version", "DSH_SKILL_FILESYSTEM_VERSION"),
    ):
        version_input = version_inputs[input_name]
        assert version_input["default"] == "next"
        assert version_input["required"] == "false"
        assert version_input["type"] == "string"
        assert step["env"][env_name] == (
            "${{ github.event.inputs." + input_name + " || 'next' }}"
        )

    run_script = step["run"]
    assert (
        'for version in "$DSH_VERSION" "$DSH_MCP_CLIENT_VERSION" '
        '"$DSH_SKILL_FILESYSTEM_VERSION";' in run_script
    )
    assert "next|latest" in run_script
    assert "published semver" in run_script
    for package_name, env_name in (
        ("dsh", "DSH_VERSION"),
        ("dsh-mcp-client", "DSH_MCP_CLIENT_VERSION"),
        ("dsh-skill-filesystem", "DSH_SKILL_FILESYSTEM_VERSION"),
    ):
        assert (
            "@deepseek-ai/" + package_name + "@${" + env_name + "}"
        ) in run_script
    assert "npm install --package-lock-only" in run_script


def test_protected_cloud_acceptance_keeps_a_fixed_codex_cli_version():
    workflow = _workflow("codex-plugin-cloud.yml")
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["jobs"]["cloud"]["environment"] == "soak-cloud"
    install = next(
        step
        for step in workflow["jobs"]["cloud"]["steps"]
        if step.get("name") == "Install the declared Runtime and pinned Codex"
    )
    assert install["env"]["CODEX_CLI_VERSION"] == "0.167.2"
    assert 'cd "$install_dir" && npm ci' in install["run"]
    assert "package-lock.json" in install["run"]
    assert "--ignore-scripts" in install["run"]
