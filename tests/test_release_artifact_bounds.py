"""Reject untrusted PyPI payloads before they choose a host or a path."""

import email.message
import importlib.util
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "value",
    [
        "http://files.pythonhosted.org/packages/x.whl",
        "https://pypi.org/packages/x.whl",
        "https://user:secret@files.pythonhosted.org/packages/x.whl",
        "https://files.pythonhosted.org:8443/packages/x.whl",
    ],
)
def test_artifact_url_rejects_any_host_but_the_reviewed_one(value):
    module = load_script("pypi_release")
    with pytest.raises(ValueError):
        module.artifact_url(value)


def test_artifact_url_pins_the_scheme_and_host_it_returns():
    module = load_script("pypi_release")
    assert module.artifact_url(
        "https://files.pythonhosted.org/packages/x.whl#sha256=deadbeef"
    ) == "https://files.pythonhosted.org/packages/x.whl"


@pytest.mark.parametrize(
    "name",
    ["../escape.whl", "/etc/passwd", "nested/../../escape.whl"],
)
def test_artifact_path_rejects_names_that_leave_dist(name, tmp_path, monkeypatch):
    module = load_script("pypi_release")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        module.artifact_path(name)


def test_artifact_path_keeps_a_plain_name_below_dist(tmp_path, monkeypatch):
    module = load_script("pypi_release")
    monkeypatch.chdir(tmp_path)
    assert module.artifact_path("qdrant_memory_mcp-0.2.9.tar.gz") == (
        tmp_path / "dist" / "qdrant_memory_mcp-0.2.9.tar.gz"
    ).resolve()


def not_found(url):
    return urllib.error.HTTPError(url, 404, "Not Found", email.message.Message(), None)


def test_release_treats_a_missing_optional_version_as_absent(monkeypatch):
    module = load_script("pypi_release")

    def urlopen(url, timeout=30):
        raise not_found(url)

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    assert module.release({"name": "qdrant-memory-mcp", "version": "0.0.0"}, required=False) is None


def test_release_keeps_polling_a_required_version_then_fails(monkeypatch):
    module = load_script("pypi_release")
    attempts = []

    def urlopen(url, timeout=30):
        attempts.append(url)
        raise not_found(url)

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError):
        module.release({"name": "qdrant-memory-mcp", "version": "0.0.0"}, required=True)
    assert len(attempts) == 12


def test_release_does_not_swallow_other_http_failures(monkeypatch):
    module = load_script("pypi_release")

    def urlopen(url, timeout=30):
        raise urllib.error.HTTPError(url, 500, "Server Error", email.message.Message(), None)

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        module.release({"name": "qdrant-memory-mcp", "version": "0.0.0"}, required=False)
