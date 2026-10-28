"""Guard the boundary between end-user MCP artifacts and test-only harnesses."""

import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_excludes_test_only_harness_artifacts():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    # Test/acceptance harness lockfiles must not ship to end users.
    assert "integrations/agent-hosts/package" not in manifest
    # Broad DSH include would pull in the contract-test package.json/lock.
    assert "recursive-include integrations/dsh *.yml *.md *.json" not in manifest
    # Node-only acceptance tests are not part of the Python sdist.
    assert "recursive-include tests *.mjs" not in manifest
    assert "tests/test_managed_bootstrap.mjs" not in manifest
    # Development-only security audits stay out of the sdist.
    assert "prune tests/dev" in manifest
    # The opt-in DSH acceptance harness needs files the sdist does not carry.
    assert "exclude tests/dsh_acceptance.py" in manifest
    assert "recursive-include tests *.py" in manifest


def test_pyproject_declares_dev_dependencies_separately():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    # Test-only dependencies live in the optional dev group, not in runtime.
    dev = project["optional-dependencies"]["dev"]
    assert any(requirement.startswith("pytest") for requirement in dev)
    # Runtime dependency stays minimal and exact.
    assert project["dependencies"] == ["hermes-plugin-qdrant-memory[mcp]==0.5.1"]


def test_dev_security_audits_live_outside_shipped_tests():
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    if sdists:
        with tarfile.open(sdists[0]) as archive:
            names = archive.getnames()
        assert not any(
            name.endswith("tests/dev/test_dsh_lock_audit.py") for name in names
        )
    else:
        # Without a built artifact, enforce the same boundary through the manifest.
        assert "prune tests/dev" in (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
