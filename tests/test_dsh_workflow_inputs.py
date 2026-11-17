"""Keep DSH compatibility overrides separate from protected release pins."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from runpy import run_path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
validate_dsh_next_audit = run_path(
    str(ROOT / "tests/dev/validate_dsh_next_audit.py")
)["validate"]


def _workflow(name):
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if "on" not in document and True in document:
        document["on"] = document.pop(True)
    return document


def test_cross_client_dispatch_defaults_to_public_runtime_and_keeps_old_fixture_optional():
    workflow = _workflow("dsh-cross-client.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["runtime_version"]["default"] == "0.7.1"
    assert inputs["runtime_version"]["options"] == ["0.6.1", "0.6.2", "0.7.1"]
    assert inputs["node_version"]["default"] == "24.9.0"
    assert inputs["python_version"]["default"] == "3.11"
    assert inputs["python_version"]["options"] == ["3.11", "3.12", "3.13", "3.14"]
    assert inputs["qdrant_client_version"]["default"] == "1.20.0"

    owner = workflow["jobs"]["owner"]
    assert owner["env"]["DSH_RUNTIME_VERSION"] == "0.7.1"
    assert owner["env"]["QDRANT_CLIENT_VERSION"] == "1.20.0"
    runtime_checkout = next(
        step["with"]
        for step in owner["steps"]
        if step.get("with", {}).get("repository") == "cnkang/hermes-plugin-qdrant-memory"
    )
    assert runtime_checkout["ref"] == "cc5cac025f5d18afb5c698b2b5db444e30fc240e"
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
        ("runtime_version", "0.7.1"),
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
        "inputs.runtime_version == '0.6.2' && "
        "'913fa705922b5bfeb29d52f102cfc6385a4d0436' || "
        "'cc5cac025f5d18afb5c698b2b5db444e30fc240e' }}"
    )


def test_dsh_next_dispatch_versions_are_optional_and_default_to_current_values():
    workflow = _workflow("dsh-next.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["dsh_version"]["default"] == "next"
    assert inputs["dsh_mcp_client_version"]["default"] == "next"
    assert inputs["dsh_skill_filesystem_version"]["default"] == "next"
    assert inputs["node_version"]["default"] == "24"
    assert inputs["python_version"]["default"] == "3.11"
    assert inputs["pnpm_version"]["default"] == "12.14.0"

    serialized = (WORKFLOWS / "dsh-next.yml").read_text(encoding="utf-8")
    for variable in (
        "DSH_MCP_CLIENT_VERSION",
        "DSH_SKILL_FILESYSTEM_VERSION",
        "pnpm_version must be an exact published semver",
        "pnpm/setup v3 requires pnpm >=11",
    ):
        assert variable in serialized

    validate = next(
        step
        for step in workflow["jobs"]["next"]["steps"]
        if step.get("name") == "Validate exact supported pnpm version"
    )
    assert validate["env"]["PNPM_VERSION"] == (
        "${{ github.event.inputs.pnpm_version || '12.14.0' }}"
    )
    assert "re.fullmatch" in validate["run"]
    assert 'int(match.group("major")) < 11' in validate["run"]

    setup = next(
        step
        for step in workflow["jobs"]["next"]["steps"]
        if step.get("name") == "Set up pnpm for the official DSH plugin manager"
    )
    assert setup["uses"] == (
        "pnpm/setup@731dfb6463bbd11c11fd0ee11fe00ed0e36d48a1"
    )
    assert setup["with"]["version"] == (
        "${{ github.event.inputs.pnpm_version || '12.14.0' }}"
    )
    assert setup["with"]["install"] is False
    assert "npm install --global" not in serialized


def test_dsh_next_audit_exception_is_limited_to_the_unpatched_upstream_advisory(tmp_path):
    workflow = _workflow("dsh-next.yml")
    audit_step = next(
        step
        for step in workflow["jobs"]["next"]["steps"]
        if step.get("name") == "Capture npm advisory report"
    )
    assert "npm audit --json" in audit_step["run"]
    assert "npm view picomatch version" in audit_step["run"]
    assert "validate_dsh_next_audit.py" in audit_step["run"]

    advisory_url = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"
    report = {
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 0,
                "moderate": 0,
                "high": 2,
                "critical": 0,
                "total": 2,
            }
        },
        "vulnerabilities": {
            "@deepseek-ai/dsh": {
                "severity": "high",
                "via": ["picomatch"],
            },
            "picomatch": {
                "severity": "high",
                "via": [{"url": advisory_url, "range": "<=4.0.7"}],
            },
        },
    }
    lock = {
        "lockfileVersion": 3,
        "packages": {"node_modules/picomatch": {"version": "4.0.7"}},
    }
    audit_path = tmp_path / "audit.json"
    lock_path = tmp_path / "package-lock.json"
    audit_path.write_text(json.dumps(report), encoding="utf-8")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    with redirect_stdout(io.StringIO()) as output:
        validate_dsh_next_audit(audit_path, lock_path, "4.0.7")
    assert advisory_url in output.getvalue()

    report["metadata"]["vulnerabilities"].update(high=3, total=3)
    report["vulnerabilities"]["another-package"] = {
        "severity": "high",
        "via": [{"url": "https://github.com/advisories/GHSA-unapproved"}],
    }
    audit_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="unapproved"):
        validate_dsh_next_audit(audit_path, lock_path, "4.0.7")

    report["metadata"]["vulnerabilities"].update(high=2, total=2)
    del report["vulnerabilities"]["another-package"]
    audit_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="4.0.8"):
        validate_dsh_next_audit(audit_path, lock_path, "4.0.8")


def test_protected_cloud_and_release_toolchains_have_no_mutable_inputs():
    for name in ("dsh-native.yml", "dsh-native-cloud.yml", "dsh-bundle-release.yml"):
        workflow = _workflow(name)
        dispatch = workflow["on"].get("workflow_dispatch") or {}
        assert dispatch.get("inputs", {}) == {}, name
        assert "${{ inputs." not in (WORKFLOWS / name).read_text(encoding="utf-8")

    cloud = _workflow("dsh-native-cloud.yml")
    assert cloud["jobs"]["cloud"]["environment"] == "soak-cloud"
    cloud_text = (WORKFLOWS / "dsh-native-cloud.yml").read_text(encoding="utf-8")
    assert "hermes-plugin-qdrant-memory[remote]==0.7.1" in cloud_text
    assert "ref: cc5cac025f5d18afb5c698b2b5db444e30fc240e" in cloud_text

    release = _workflow("dsh-bundle-release.yml")
    build_steps = release["jobs"]["build"]["steps"]
    node_setup = next(step for step in build_steps if "setup-node" in step.get("uses", ""))
    assert node_setup["with"]["node-version"] == "24.9.0"
    python_setup = next(step for step in build_steps if "setup-python" in step.get("uses", ""))
    assert python_setup["with"]["python-version"] == "3.11"
