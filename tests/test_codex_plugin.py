"""Portable package invariants and thin Node host-boundary behavior."""

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "codex_package", ROOT / "scripts/build_codex_plugin.py"
)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_portable_package():
    assert package.validate()["version"] == "0.1.0"
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/qdrant-memory"
    release = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())
    assert len(release["runtime_commit"]) == len(release["skill_commit"]) == 40
    requirements = (ROOT / "plugins/qdrant-memory/requirements.txt").read_text()
    assert release["runtime_commit"] in requirements
    assert "qdrant-memory-mcp==" + release["mcp_distribution_version"] in requirements


def test_node_paths_do_not_reuse_hermes():
    script = """
import { locations } from './plugins/qdrant-memory/launcher.mjs';
const paths = locations({}, '/example/user', 'linux');
if (paths.profile !== '/example/user/.qdrant-memory/codex/profile') process.exit(2);
try { locations({QDRANT_MEMORY_CODEX_ROOT: 'relative'}, '/example/user', 'linux'); process.exit(3); }
catch { console.log('PASS'); }
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "PASS"


def test_missing_runtime_fails_without_writes(tmp_path):
    import os

    env = {**os.environ, "QDRANT_MEMORY_CODEX_ROOT": str(tmp_path / "absent")}
    result = subprocess.run(
        ["node", str(ROOT / "plugins/qdrant-memory/launcher.mjs"), "mcp"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "No data was reset" in result.stderr
    assert not (tmp_path / "absent").exists()
