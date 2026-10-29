"""The DSH bundle stays a configuration-only, exactly pinned layer."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def packer():
    spec = importlib.util.spec_from_file_location("pack_dsh_bundle", ROOT / "scripts/pack_dsh_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_manifest_and_patch_contract():
    meta = json.loads((ROOT / "integrations/dsh/bundle/package.json").read_text(encoding="utf-8"))
    launcher = json.loads((ROOT / "launcher-source.json").read_text(encoding="utf-8"))
    assert meta["name"] == "@cnkang/qdrant-memory-dsh-bundle"
    assert meta["version"] == "0.1.5"
    assert meta["license"] == "MIT"
    assert meta.get("private") is not True
    assert meta["dsh"] == {"bundle": {"patch": "./cordis.patch.yml"}}
    assert set(meta["files"]) == {"cordis.patch.yml", "README.md", "LICENSE"}
    assert meta["peerDependencies"] == {"@deepseek-ai/dsh-mcp-client": ">=0.2.0-rc.2 <0.3.0 || >=0.2.1-rc.2 <0.3.0"}
    assert meta["repository"]["directory"] == "integrations/dsh/bundle"
    patch = (ROOT / "integrations/dsh/bundle/cordis.patch.yml").read_text(encoding="utf-8")
    assert patch.count("- insert:") == 1
    assert "id: cnkang-qdrant-memory-mcp" in patch
    assert "name: '@deepseek-ai/dsh-mcp-client'" in patch
    assert "serverName: qdrant-memory" in patch
    assert "command: npx" in patch
    assert f"'{launcher['name']}@{launcher['version']}'" in patch
    # DSH provisioning stays an explicit prepare step; the probe must not
    # download, and the local preset needs no credential injection.
    assert "--auto-setup" not in patch
    assert "!!js" not in patch and "env:" not in patch
    assert "reconnect:" not in patch
    assert (ROOT / "integrations/dsh/bundle/LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize("bad", ["extra", "symlink", "changed", "missing"])
def test_bundle_distribution_rejects_unreviewed_payload(tmp_path, bad):
    module = packer()
    archive = tmp_path / "package.tgz"
    with tarfile.open(archive, "w:gz") as output:
        for name in sorted(module.FILES | ({"secrets.env"} if bad == "extra" else set())):
            if bad == "missing" and name == "README.md":
                continue
            path = ROOT / "integrations/dsh/bundle" / name
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
    module = packer()
    source = tmp_path / "bundle"
    source.mkdir()
    for name in module.FILES:
        (source / name).write_bytes((ROOT / "integrations/dsh/bundle" / name).read_bytes())
    (source / "package.json").write_text(json.dumps({"name": "x", "version": "0.0.0", "dsh": {"bundle": {"patch": "./other.yml"}}}))
    archive = tmp_path / "package.tgz"
    with tarfile.open(archive, "w:gz") as output:
        for name in sorted(module.FILES):
            data = (source / name).read_bytes()
            member = tarfile.TarInfo("package/" + name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match="patch"):
        module.inspect(archive, source)
