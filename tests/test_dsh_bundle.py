"""The unified DSH Host bundle keeps one reviewed payload and storage target."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def packer():
    """Load the DSH bundle packaging module."""
    spec = importlib.util.spec_from_file_location("pack_dsh_bundle", ROOT / "scripts/pack_dsh_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_manifest_and_patch_contract():
    """Validate the DSH package manifest, files, and patch contract."""
    meta = json.loads((ROOT / "integrations/dsh/bundle/package.json").read_text(encoding="utf-8"))
    launcher = json.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))
    assert meta["name"] == "@cnkang/qdrant-memory-dsh-bundle"
    assert meta["version"] == "0.2.0-rc.1"
    assert meta["license"] == "MIT"
    assert meta.get("private") is not True
    assert meta["dsh"] == {"bundle": {"patch": "./cordis.patch.yml"}}
    assert set(meta["files"]) == packer().FILES - {'package.json'}
    assert meta['dependencies']['@deepseek-ai/dsh-mcp-client'] == '0.2.2-rc.1'
    assert meta['engines']['node'] == '>=24.9.0'
    assert meta["repository"]["directory"] == "integrations/dsh/bundle"
    patch = (ROOT / "integrations/dsh/bundle/cordis.patch.yml").read_text(encoding="utf-8")
    assert patch.count("- insert:") == 1
    assert "id: cnkang-qdrant-memory-mcp" in patch
    assert "name: '@cnkang/qdrant-memory-dsh-bundle'" in patch
    assert 'mode: legacy' in patch
    assert patch.count('enabled: false') == 3
    host = (ROOT / 'integrations/dsh/bundle/index.js').read_text()
    assert f"'{launcher['name']}@{launcher['version']}'" in host
    # DSH provisioning stays an explicit prepare step; the probe must not
    # download, and the local preset needs no credential injection.
    assert "--auto-setup" not in patch
    assert "!!js" not in patch
    assert "env:" not in patch
    assert "reconnect:" not in patch
    assert (ROOT / "integrations/dsh/bundle/LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize('version', ['../escape', '0.2.0/escape', '01.2.0', '0.2.0-rc.0', '0.2.0+unreviewed'])
def test_bundle_identity_rejects_path_and_unreviewed_versions(version):
    module = packer()
    with pytest.raises(ValueError, match='identity'):
        module.validate_identity({'name': '@cnkang/qdrant-memory-dsh-bundle', 'version': version})


@pytest.mark.parametrize("bad", ["extra", "symlink", "changed", "missing"])
def test_bundle_distribution_rejects_unreviewed_payload(tmp_path, bad):
    """Reject DSH archives with unreviewed, missing, or unsafe files."""
    module = packer()
    archive = tmp_path / "package.tgz"
    with tarfile.open(archive, "w:gz") as output:
        for name in sorted(module.FILES | ({"secrets.env"} if bad == "extra" else set())):
            if bad == "missing" and name == "README.md":
                continue
            path = module.payload_path(ROOT / "integrations/dsh/bundle", name)
            data = path.read_bytes() if name in module.FILES else b"private"
            if bad == "changed" and name == "cordis.patch.yml":
                data = b"[]"
            member = tarfile.TarInfo("package/" + name)
            member.mode = 0o644
            if bad == "symlink" and name == "cordis.patch.yml":
                member.type, member.linkname = tarfile.SYMTYPE, "/tmp/patch.yml"
            else:
                member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError):
        module.inspect(archive, ROOT / "integrations/dsh/bundle")


def test_bundle_inspect_rejects_manifest_without_reviewed_patch(tmp_path, monkeypatch):
    """Reject an archive whose manifest selects an unreviewed patch."""
    module = packer()
    source = tmp_path / "bundle"
    source.mkdir()
    for name in module.FILES:
        target = module.payload_path(source, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(module.payload_path(ROOT / "integrations/dsh/bundle", name).read_bytes())
    (source / "package.json").write_text(json.dumps({"name": "x", "version": "0.0.0", "dsh": {"bundle": {"patch": "./other.yml"}}}))
    archive = tmp_path / "package.tgz"
    with tarfile.open(archive, "w:gz") as output:
        for name in sorted(module.FILES):
            data = module.payload_path(source, name).read_bytes()
            member = tarfile.TarInfo("package/" + name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match="patch"):
        module.inspect(archive, source)
