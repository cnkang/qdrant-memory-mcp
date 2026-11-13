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
            if step.get("name") == "Install fixed hash-locked Codex CLI version"
        )
        assert step["env"]["CODEX_CLI_VERSION"] == "0.167.2"
        assert '.github/codex-cli-locks/${CODEX_CLI_VERSION}' in step["run"]
        assert 'cd "$install_dir" && npm ci' in step["run"]
        assert "package-lock.json" in step["run"]
        assert "--ignore-scripts" in step["run"]
        assert "node_modules/.bin" in step["run"]

    compatibility = workflow["jobs"]["compatibility-probe"]
    assert compatibility["if"] == (
        "${{ github.event_name == 'workflow_dispatch' && "
        "(inputs.node_version != '22' || inputs.python_version != '3.11' || "
        "inputs.codex_cli_version != '0.167.2') }}"
    )
    selected = next(
        step
        for step in compatibility["steps"]
        if step.get("name") == "Install selected hash-locked Codex CLI version"
    )
    assert (
        compatibility["env"]["CODEX_CLI_VERSION"]
        == "${{ inputs.codex_cli_version || '0.167.2' }}"
    )
    assert '.github/codex-cli-locks/${CODEX_CLI_VERSION}' in selected["run"]
    assert 'cd "$install_dir" && npm ci' in selected["run"]
    assert "package-lock.json" in selected["run"]
    assert "--ignore-scripts" in selected["run"]


def test_codex_toolchain_versions_are_optional_and_have_validated_defaults():
    workflow = _workflow("codex-plugin.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["node_version"]["default"] == "22"
    assert inputs["node_version"]["required"] == "false"
    assert inputs["node_version"]["type"] == "choice"
    assert inputs["node_version"]["options"] == ["22", "24"]
    assert inputs["python_version"]["default"] == "3.11"
    assert inputs["python_version"]["required"] == "false"
    assert inputs["python_version"]["type"] == "choice"
    assert inputs["python_version"]["options"] == ["3.11", "3.14"]
    for job_name in ("portable", "merged-package", "lifecycle-e2e"):
        steps = workflow["jobs"][job_name]["steps"]
        node_setup = next(
            step for step in steps if step.get("uses", "").startswith("actions/setup-node@")
        )
        python_setup = next(
            step for step in steps if step.get("uses", "").startswith("actions/setup-python@")
        )
        assert node_setup["with"]["node-version"] == "22"
        assert python_setup["with"]["python-version"] == "3.11"
        assert "inputs." not in json.dumps(workflow["jobs"][job_name])

    compatibility = workflow["jobs"]["compatibility-probe"]
    assert compatibility["name"] == "Optional manual toolchain compatibility probe"
    assert compatibility["env"] == {
        "CODEX_PLUGIN_NODE_VERSION": "${{ inputs.node_version || '22' }}",
        "CODEX_PLUGIN_PYTHON_VERSION": "${{ inputs.python_version || '3.11' }}",
        "CODEX_CLI_VERSION": "${{ inputs.codex_cli_version || '0.167.2' }}",
    }
    validation = next(
        step
        for step in compatibility["steps"]
        if step.get("name") == "Validate selected compatibility versions"
    )
    assert "22|24" in validation["run"]
    assert "3.11|3.14" in validation["run"]
    assert "0.167.2|0.165.0" in validation["run"]
    node_setup = next(
        step
        for step in compatibility["steps"]
        if step.get("uses", "").startswith("actions/setup-node@")
    )
    python_setup = next(
        step
        for step in compatibility["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert node_setup["with"]["node-version"] == "${{ env.CODEX_PLUGIN_NODE_VERSION }}"
    assert python_setup["with"]["python-version"] == "${{ env.CODEX_PLUGIN_PYTHON_VERSION }}"


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
    node_setup = next(
        step
        for step in workflow["jobs"]["cloud"]["steps"]
        if step.get("uses", "").startswith("actions/setup-node@")
    )
    python_setup = next(
        step
        for step in workflow["jobs"]["cloud"]["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert node_setup["with"]["node-version"] == "22"
    assert python_setup["with"]["python-version"] == "3.11"
    assert 'cd "$install_dir" && npm ci' in install["run"]
    assert "package-lock.json" in install["run"]
    assert "--ignore-scripts" in install["run"]
