"""Keep DSH compatibility overrides separate from protected release pins."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def _workflow(name):
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if "on" not in document and True in document:
        document["on"] = document.pop(True)
    return document


def test_cross_client_dispatch_defaults_to_public_runtime_and_keeps_old_fixture_optional():
    workflow = _workflow("dsh-cross-client.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["runtime_version"]["default"] == "0.6.2"
    assert inputs["runtime_version"]["options"] == ["0.6.1", "0.6.2"]
    assert inputs["node_version"]["default"] == "24.9.0"
    assert inputs["python_version"]["default"] == "3.11"
    assert inputs["python_version"]["options"] == ["3.11", "3.12", "3.13", "3.14"]
    assert inputs["qdrant_client_version"]["default"] == "1.20.0"

    owner = workflow["jobs"]["owner"]
    assert owner["env"]["DSH_RUNTIME_VERSION"] == "0.6.2"
    assert owner["env"]["QDRANT_CLIENT_VERSION"] == "1.20.0"
    runtime_checkout = next(
        step["with"]
        for step in owner["steps"]
        if step.get("with", {}).get("repository") == "cnkang/hermes-plugin-qdrant-memory"
    )
    assert runtime_checkout["ref"] == "913fa705922b5bfeb29d52f102cfc6385a4d0436"
    node_setup = next(step["with"] for step in owner["steps"] if "setup-node" in step.get("uses", ""))
    python_setup = next(step["with"] for step in owner["steps"] if "setup-python" in step.get("uses", ""))
    assert node_setup["node-version"] == "24.9.0"
    assert python_setup["python-version"] == "3.11"
    assert "inputs." not in str(owner)

    compatibility = workflow["jobs"]["compatibility"]
    assert compatibility["name"] == "Manual DSH compatibility probe (not release evidence)"
    assert compatibility["needs"] == "owner"
    assert "github.event_name == 'workflow_dispatch'" in compatibility["if"]
    for field, default in (
        ("runtime_version", "0.6.2"),
        ("node_version", "24.9.0"),
        ("python_version", "3.11"),
        ("qdrant_client_version", "1.20.0"),
    ):
        assert f"inputs.{field} != '{default}'" in compatibility["if"]
    assert compatibility["env"]["DSH_RUNTIME_VERSION"] == "${{ inputs.runtime_version }}"
    assert compatibility["env"]["QDRANT_CLIENT_VERSION"] == "${{ inputs.qdrant_client_version }}"
    compatibility_checkout = next(
        step["with"]
        for step in compatibility["steps"]
        if step.get("with", {}).get("repository") == "cnkang/hermes-plugin-qdrant-memory"
    )
    assert compatibility_checkout["ref"] == (
        "${{ inputs.runtime_version == '0.6.1' && "
        "'2696122405e3324a1e227c131e0f9b2a320dd23c' || "
        "'913fa705922b5bfeb29d52f102cfc6385a4d0436' }}"
    )


def test_dsh_next_dispatch_versions_are_optional_and_default_to_current_values():
    workflow = _workflow("dsh-next.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["dsh_version"]["default"] == "next"
    assert inputs["dsh_mcp_client_version"]["default"] == "next"
    assert inputs["dsh_skill_filesystem_version"]["default"] == "next"
    assert inputs["node_version"]["default"] == "24"
    assert inputs["python_version"]["default"] == "3.11"
    assert inputs["pnpm_version"]["default"] == ""

    serialized = (WORKFLOWS / "dsh-next.yml").read_text(encoding="utf-8")
    for variable in (
        "DSH_MCP_CLIENT_VERSION",
        "DSH_SKILL_FILESYSTEM_VERSION",
        "pnpm_version must be an exact published semver",
        "pnpm@12.14.0",
    ):
        assert variable in serialized


def test_protected_cloud_and_release_toolchains_have_no_mutable_inputs():
    for name in ("dsh-native.yml", "dsh-native-cloud.yml", "dsh-bundle-release.yml"):
        workflow = _workflow(name)
        dispatch = workflow["on"].get("workflow_dispatch") or {}
        assert dispatch.get("inputs", {}) == {}, name
        assert "${{ inputs." not in (WORKFLOWS / name).read_text(encoding="utf-8")

    cloud = _workflow("dsh-native-cloud.yml")
    assert cloud["jobs"]["cloud"]["environment"] == "soak-cloud"
    cloud_text = (WORKFLOWS / "dsh-native-cloud.yml").read_text(encoding="utf-8")
    assert "hermes-plugin-qdrant-memory[remote]==0.6.2" in cloud_text
    assert "ref: 913fa705922b5bfeb29d52f102cfc6385a4d0436" in cloud_text

    release = _workflow("dsh-bundle-release.yml")
    build_steps = release["jobs"]["build"]["steps"]
    node_setup = next(step for step in build_steps if "setup-node" in step.get("uses", ""))
    assert node_setup["with"]["node-version"] == "24.9.0"
    python_setup = next(step for step in build_steps if "setup-python" in step.get("uses", ""))
    assert python_setup["with"]["python-version"] == "3.11"
