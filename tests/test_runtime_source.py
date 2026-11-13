"""Public release wins over the preparation-only immutable source fallback."""

import io
import json
import re
import urllib.error

import pytest

import pathlib

from test_release_guards import load_script


def test_cross_harness_checkouts_match_selected_runtime_source():
    """The host gates must install the same Runtime release as the distribution."""
    root = pathlib.Path(__file__).resolve().parents[1]
    source = json.loads((root / "runtime-source.json").read_text())
    workflow = (root / ".github/workflows/cross-harness.yml").read_text()
    # The workflow uses literal adjacent repository/ref fields. Check every
    # Runtime checkout without adding a YAML dependency to package acceptance.
    repository = r"(?m)^\s+repository: cnkang/hermes-plugin-qdrant-memory\s*\n"
    checkouts = re.findall(repository + r"\s+ref: ([^\s#]+)", workflow)
    assert len(checkouts) == len(re.findall(repository, workflow)) > 0
    assert all(revision == source["commit"] for revision in checkouts)


def test_sonar_coverage_runtime_pin_matches_distribution_source():
    """Coverage dependencies must use the Runtime release pinned by the distribution."""
    root = pathlib.Path(__file__).resolve().parents[1]
    source = json.loads((root / "runtime-source.json").read_text())
    requirements = (root / ".github/requirements-sonar-ci.in").read_text()
    lock = (root / ".github/requirements-sonar-ci.txt").read_text()
    source_pins = re.findall(
        r"(?m)^hermes-plugin-qdrant-memory\[mcp\]==([^\s#]+)\s*$",
        requirements,
    )
    locked_pins = re.findall(
        r"(?m)^hermes-plugin-qdrant-memory==([^\s\\]+)\s+\\$",
        lock,
    )
    assert source_pins == [source["version"]]
    assert locked_pins == [source["version"]]


def test_public_runtime_avoids_clone(monkeypatch):
    """Use the public pinned Runtime wheel without cloning a source fallback."""
    module = load_script("prepare_runtime")
    root = pathlib.Path(__file__).resolve().parents[1]
    source = json.loads((root / "runtime-source.json").read_text())
    commands = []
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"{}")
    )
    monkeypatch.setattr(module.subprocess, "run", lambda cmd, **k: commands.append(cmd))
    module.main(root=root)
    assert len(commands) == 1
    assert "download" in commands[0]
    assert commands[0][-1] == f"hermes-plugin-qdrant-memory=={source['version']}"


def test_runtime_lookup_error_does_not_silently_fallback(monkeypatch):
    """Keep non-404 index errors visible instead of switching installation source."""
    module = load_script("prepare_runtime")

    def forbidden(*args, **kwargs):
        """Return a controlled index authorization failure without contacting PyPI."""
        raise urllib.error.HTTPError(
            "https://example.invalid", 403, "forbidden", {}, None
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
    with pytest.raises(urllib.error.HTTPError):
        module.main()


def test_foreign_runtime_repository_is_rejected(monkeypatch, tmp_path):
    """The preparation fallback may only clone the canonical runtime repository."""
    module = load_script("prepare_runtime")
    (tmp_path / "runtime-source.json").write_text(
        json.dumps(
            {
                "repository": "https://example.invalid/attacker/runtime.git",
                "commit": "0" * 40,
                "version": "9.9.9",
            }
        )
    )

    def absent(*args, **kwargs):
        """Make the version lookup select the source fallback."""
        raise urllib.error.HTTPError("https://example.invalid", 404, "absent", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", absent)
    with pytest.raises(ValueError, match="canonical repository"):
        module.main(tmp_path)


def test_pull_request_disables_the_source_fallback(monkeypatch, tmp_path):
    """Unreviewed pull requests must exercise the published runtime, not a build."""
    module = load_script("prepare_runtime")
    source = json.loads((pathlib.Path(__file__).resolve().parents[1] / "runtime-source.json").read_text())
    (tmp_path / "runtime-source.json").write_text(json.dumps(source))

    def absent(*args, **kwargs):
        """Make the version lookup select the source fallback."""
        raise urllib.error.HTTPError("https://example.invalid", 404, "absent", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", absent)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    with pytest.raises(ValueError, match="disabled for pull requests"):
        module.main(tmp_path)
