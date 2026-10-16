"""Public release wins over the preparation-only immutable source fallback."""

import io
import urllib.error

import pytest

from test_release_guards import load_script


def test_public_runtime_avoids_clone(monkeypatch):
    """Use the public pinned Runtime wheel without cloning a source fallback."""
    module = load_script("prepare_runtime")
    commands = []
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"{}")
    )
    monkeypatch.setattr(module.subprocess, "run", lambda cmd, **k: commands.append(cmd))
    module.main()
    assert len(commands) == 1 and "download" in commands[0]
    assert commands[0][-1] == "hermes-plugin-qdrant-memory==0.3.0"


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
