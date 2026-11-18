"""The published-payload check accepts the release and rejects any drift."""

import base64
import hashlib
import importlib.util
import io
import json
import tarfile
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


def integrity(body):
    """Return the npm SRI value for bytes."""
    return "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode("ascii")


def build(tmp_path, files, extra=None):
    """Write a launcher source tree and return it with a matching tarball."""
    source = tmp_path / "managed"
    source.mkdir()
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
    members = {"package/package.json": json.dumps(package).encode()}
    members["package/runtime.json"] = json.dumps(runtime).encode()
    for name, content in files.items():
        members[f"package/{name}"] = content
    members.update(extra or {})
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    body = buffer.getvalue()
    pin = {
        "name": package["name"],
        "version": package["version"],
        "runtime_version": runtime["version"],
        "integrity": integrity(body),
    }
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


@pytest.mark.parametrize("mutation", ["integrity", "content", "unexpected", "missing"])
def test_published_payload_rejects_drift(tmp_path, mutation):
    """Reject a different integrity, changed file, extra member or missing file."""
    source, pin, body = build(
        tmp_path,
        {"launcher.mjs": b"#!/usr/bin/env node\n", "requirements.lock": b"x==1\n"},
    )
    if mutation == "integrity":
        pin["integrity"] = integrity(b"other")
    elif mutation == "content":
        (source / "launcher.mjs").write_bytes(b"changed\n")
    elif mutation == "unexpected":
        extra_buffer = io.BytesIO()
        with tarfile.open(fileobj=extra_buffer, mode="w:gz") as archive:
            for name, content in {
                "package/extra.txt": b"extra",
                "package/launcher.mjs": b"#!/usr/bin/env node\n",
                "package/requirements.lock": b"x==1\n",
                "package/package.json": json.dumps(
                    {
                        "name": "@cnkang/qdrant-memory-launcher",
                        "version": "0.1.0-rc.13",
                        "files": ["launcher.mjs", "requirements.lock"],
                    }
                ).encode(),
                "package/runtime.json": json.dumps({"version": "0.7.2"}).encode(),
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        body = extra_buffer.getvalue()
        pin["integrity"] = integrity(body)
    else:
        missing_buffer = io.BytesIO()
        with tarfile.open(fileobj=missing_buffer, mode="w:gz") as archive:
            for name, content in {
                "package/launcher.mjs": b"#!/usr/bin/env node\n",
                "package/package.json": json.dumps(
                    {
                        "name": "@cnkang/qdrant-memory-launcher",
                        "version": "0.1.0-rc.13",
                        "files": ["launcher.mjs", "requirements.lock"],
                    }
                ).encode(),
                "package/runtime.json": json.dumps({"version": "0.7.2"}).encode(),
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        body = missing_buffer.getvalue()
        pin["integrity"] = integrity(body)
    with pytest.raises(ValueError):
        verifier().verify(body, pin, source)
