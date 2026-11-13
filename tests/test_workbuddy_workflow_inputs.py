"""Keep WorkBuddy CI compatibility selectors separate from release pins."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _workflow(name):
    """Load a workflow while avoiding YAML 1.1's boolean interpretation of `on`."""
    document = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
    if "on" not in document and True in document:
        document["on"] = document.pop(True)
    return document


def test_preview_inputs_select_only_compatibility_toolchains():
    workflow = _workflow("workbuddy-preview.yml")
    dispatch = workflow["on"]["workflow_dispatch"]
    inputs = dispatch["inputs"]

    assert set(inputs) == {"python_version", "node_version"}
    assert inputs["python_version"] == {
        "description": "Python interpreter for compatibility tests; product Runtime pins stay locked",
        "required": False,
        "default": "3.11",
        "type": "choice",
        "options": ["3.11", "3.14"],
    }
    assert inputs["node_version"] == {
        "description": "Node.js interpreter for compatibility tests; WorkBuddy's managed runtime stays at Node 20",
        "required": False,
        "default": "20",
        "type": "choice",
        "options": ["20", "22", "24"],
    }

    steps = workflow["jobs"]["connector"]["steps"]
    python_setup = next(step for step in steps if str(step.get("uses", "")).startswith("actions/setup-python@"))
    node_setup = next(step for step in steps if str(step.get("uses", "")).startswith("actions/setup-node@"))
    assert python_setup["with"]["python-version"] == "${{ inputs.python_version || '3.11' }}"
    assert node_setup["with"]["node-version"] == "${{ inputs.node_version || '20' }}"

    # The selectable versions are test-host runtimes only. Product versions and
    # npm integrity continue to come from reviewed, immutable source pins.
    launcher = json.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))
    mcp = json.loads((ROOT / "integrations/workbuddy/mcp.json").read_text(encoding="utf-8"))
    skill = json.loads((ROOT / "integrations/workbuddy/skill-source.json").read_text(encoding="utf-8"))
    server = mcp["mcpServers"]["qdrant-memory"]
    assert server["runtime"] == {"type": "node", "version": "20"}
    assert server["args"][1] == f"{launcher['name']}@{launcher['version']}"
    assert server["npmRegistries"] == ["https://registry.npmjs.org"]
    assert launcher["integrity"].startswith("sha512-")
    assert len(skill["commit"]) == 40


def test_release_python_toolchain_remains_fixed():
    workflow = _workflow("workbuddy-release.yml")
    steps = workflow["jobs"]["build"]["steps"]
    python_setup = next(step for step in steps if str(step.get("uses", "")).startswith("actions/setup-python@"))
    assert python_setup["with"]["python-version"] == "3.11"
