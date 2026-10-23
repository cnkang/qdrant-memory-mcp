"""The npm distribution excludes local data and contains a usable executable."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def packer():
    spec = importlib.util.spec_from_file_location("pack_launcher", ROOT / "scripts/pack_launcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("bad", ["extra", "symlink", "changed", "entry-mode", "missing"])
def test_distribution_rejects_unreviewed_payload(tmp_path, bad):
    module = packer()
    archive = tmp_path / "package.tgz"
    with tarfile.open(archive, "w:gz") as output:
        for name in sorted(module.FILES | ({".env"} if bad == "extra" else set())):
            if bad == "missing" and name == "LICENSE":
                continue
            path = ROOT / "integrations/managed" / name
            data = path.read_bytes() if name in module.FILES else b"private"
            if bad == "changed" and name == "runtime.json":
                data = b"{}"
            member = tarfile.TarInfo("package/" + name)
            member.mode = 0o755 if name == "launcher.mjs" else 0o644
            if bad == "entry-mode":
                member.mode = 0o644
            if bad == "symlink" and name == "runtime.json":
                member.type, member.linkname = tarfile.SYMTYPE, "/tmp/runtime.json"
            else:
                member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError):
        module.inspect(archive, ROOT / "integrations/managed")


def test_launcher_manifest_and_license_match_distribution():
    module = packer()
    source = ROOT / "integrations/managed"
    meta = json.loads((source / "package.json").read_text())
    assert set(meta["files"]) | {"package.json"} == module.FILES
    assert meta["bin"] == {"qdrant-memory-launcher": "launcher.mjs"}
    assert meta["engines"] == {"node": ">=20"}
    assert (source / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


def test_managed_lock_keeps_pillow_security_version_and_compatibility_hash():
    source = ROOT / "integrations/managed"
    lock = (source / "requirements.lock").read_text()
    assert "pillow==13.0.0 \\\n" in lock
    metadata = json.loads((source / "runtime.json").read_text())
    compat = metadata["fastembed_compat"]
    assert "fastembed==0.9.0+qm.pillow13 \\\n" in lock
    assert "--hash=sha256:" + compat["wheel_sha256"] in lock
    assert metadata["version"] == "0.5.0"
