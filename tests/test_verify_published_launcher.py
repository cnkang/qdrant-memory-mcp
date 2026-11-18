"""The published-payload check accepts the release and rejects any drift."""

import base64
import hashlib
import importlib.util
import io
import json
import tarfile
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def verifier():
    """Load the published launcher verification module."""
    spec = importlib.util.spec_from_file_location(
        "verify_published_launcher", ROOT / "scripts/verify_published_launcher.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    """Minimal stand-in for one urllib response."""

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self.payload


def integrity(body):
    """Return the npm SRI value for bytes."""
    return "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode("ascii")


def tarball(members):
    """Return gzip-compressed tar bytes for the given members."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def build(root, files, members=None):
    """Write a launcher source tree and its pin under a repository root."""
    source = root / "integrations/managed"
    source.mkdir(parents=True)
    for name, content in files.items():
        (source / name).write_bytes(content)
    package = {
        "name": "@cnkang/qdrant-memory-launcher",
        "version": "0.1.0-rc.13",
        "files": sorted(files),
    }
    runtime = {"version": "0.7.2"}
    (source / "package.json").write_bytes(json.dumps(package).encode())
    (source / "runtime.json").write_bytes(json.dumps(runtime).encode())
    default = {
        "package/package.json": json.dumps(package).encode(),
        "package/runtime.json": json.dumps(runtime).encode(),
    }
    default.update({f"package/{name}": content for name, content in files.items()})
    body = tarball(members if members is not None else default)
    pin = {
        "name": package["name"],
        "version": package["version"],
        "runtime_version": runtime["version"],
        "integrity": integrity(body),
    }
    (root / "launcher-source.json").write_text(json.dumps(pin), encoding="utf-8")
    return source, pin, body


def test_published_payload_matches_the_checkout(tmp_path):
    """A matching tarball reports its identity."""
    source, pin, body = build(
        tmp_path,
        {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"},
    )
    result = verifier().verify(body, pin, source)
    assert result == {
        "name": pin["name"],
        "version": pin["version"],
        "integrity": pin["integrity"],
    }


def test_registry_metadata_escapes_the_package_name():
    """The registry lookup uses the scoped name and returns the document."""
    module = verifier()
    document = {"dist": {"integrity": "sha512-x", "tarball": "https://example/t.tgz"}}
    seen = {}

    def opener(url, timeout):
        seen["url"] = url
        return Response(json.dumps(document).encode())

    result = module.registry_metadata(
        "@cnkang/qdrant-memory-launcher", "0.1.0-rc.13", opener
    )
    assert result == document
    assert seen["url"] == (
        "https://registry.npmjs.org/@cnkang%2fqdrant-memory-launcher/0.1.0-rc.13"
    )


def test_registry_metadata_reports_an_unpublished_version():
    """An absent version explains that publication must happen first."""
    module = verifier()

    def opener(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    with pytest.raises(SystemExit) as error:
        module.registry_metadata("@cnkang/qdrant-memory-launcher", "9.9.9", opener)
    assert "is not published" in str(error.value)


def test_registry_metadata_propagates_other_errors():
    """A non-404 registry failure is not reported as an unpublished package."""
    module = verifier()

    def opener(url, timeout):
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        module.registry_metadata(
            "@cnkang/qdrant-memory-launcher", "0.1.0-rc.13", opener
        )


def test_download_returns_tarball_bytes():
    """The tarball download returns the raw response body."""
    module = verifier()
    assert (
        module.download(
            "https://example/t.tgz", lambda url, timeout: Response(b"bytes")
        )
        == b"bytes"
    )


def test_main_verifies_the_pinned_tarball(tmp_path, capsys, monkeypatch):
    """The command prints the verified identity for a matching release."""
    module = verifier()
    _, pin, body = build(
        tmp_path,
        {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"},
    )
    monkeypatch.setattr(
        module,
        "registry_metadata",
        lambda name, version: {"dist": {"integrity": pin["integrity"], "tarball": "u"}},
    )
    monkeypatch.setattr(module, "download", lambda url: body)
    assert module.main(["--root", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == {
        "name": pin["name"],
        "version": pin["version"],
        "integrity": pin["integrity"],
    }


def test_main_rejects_a_registry_integrity_mismatch(tmp_path, monkeypatch):
    """A registry document that disagrees with the pin stops the check."""
    module = verifier()
    build(
        tmp_path,
        {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"},
    )
    monkeypatch.setattr(
        module,
        "registry_metadata",
        lambda name, version: {"dist": {"integrity": "sha512-other", "tarball": "u"}},
    )
    with pytest.raises(ValueError):
        module.main(["--root", str(tmp_path)])


@pytest.mark.parametrize(
    "mutation", ["integrity", "content", "unexpected", "missing", "unsafe"]
)
def test_published_payload_rejects_drift(tmp_path, mutation):
    """Reject a different integrity, changed file, extra member or missing file."""
    files = {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"}
    package = {
        "name": "@cnkang/qdrant-memory-launcher",
        "version": "0.1.0-rc.13",
        "files": ["launcher.mjs", "requirements.lock"],
    }
    complete = {
        "package/launcher.mjs": files["launcher.mjs"],
        "package/requirements.lock": files["requirements.lock"],
        "package/package.json": json.dumps(package).encode(),
        "package/runtime.json": json.dumps({"version": "0.7.2"}).encode(),
    }
    members = None
    if mutation == "unexpected":
        members = {**complete, "package/extra.txt": b"extra"}
    elif mutation == "missing":
        members = {
            key: value
            for key, value in complete.items()
            if not key.endswith("requirements.lock")
        }
    elif mutation == "unsafe":
        members = {
            "package/../escape.txt": b"x",
            "package/runtime.json": complete["package/runtime.json"],
        }
    source, pin, body = build(tmp_path, files, members)
    if mutation == "integrity":
        pin["integrity"] = integrity(b"other")
    elif mutation == "content":
        (source / "launcher.mjs").write_bytes(b"changed\n")
    with pytest.raises(ValueError):
        verifier().verify(body, pin, source)


def test_missing_source_file_is_rejected(tmp_path):
    """A payload file that no longer exists in the checkout fails the check."""
    source, pin, body = build(
        tmp_path,
        {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"},
    )
    (source / "launcher.mjs").unlink()
    with pytest.raises(ValueError):
        verifier().verify(body, pin, source)


def test_runtime_drift_with_the_checkout_is_rejected(tmp_path):
    """A checkout runtime.json that differs from the published one fails."""
    source, pin, body = build(
        tmp_path,
        {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"},
    )
    (source / "runtime.json").write_text('{"version": "0.7.1"}', encoding="utf-8")
    with pytest.raises(ValueError):
        verifier().verify(body, pin, source)
