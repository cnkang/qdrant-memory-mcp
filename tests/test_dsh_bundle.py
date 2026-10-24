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
    assert meta["version"] == "0.1.4"
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


def at_least(version, floor):
    """A prerelease of the fix version does not count as the fix."""
    numbers, _, prerelease = version.partition("-")
    parts = tuple(int(part) for part in numbers.split("."))
    return parts > floor or (parts == floor and not prerelease)


def test_dsh_lock_excludes_oauth_vulnerable_sdk_versions():
    """Reject vulnerable SDK copies, including nested transitive resolutions."""
    lock = json.loads((ROOT / "integrations/dsh/package-lock.json").read_text(encoding="utf-8"))
    clients = []
    for path, package in lock["packages"].items():
        if path.endswith(("node_modules/@modelcontextprotocol/client", "node_modules/@modelcontextprotocol/core")):
            floor = (2, 3, 0) if path.endswith("/client") else (2, 2, 0)
            assert at_least(
                package["version"], floor
            ), f"{path} retains an OAuth or cross-origin redirect advisory baseline"
            if path.endswith("/client"):
                clients.append(path)
        elif path.endswith("node_modules/@modelcontextprotocol/sdk"):
            assert at_least(
                package["version"], (1, 32, 0)
            ), f"{path} retains the affected 1.x SDK"
    assert clients, "The actual DSH MCP client resolution must be audited"


def test_dsh_lock_excludes_vulnerable_http_and_schema_versions():
    """Reject affected undici and Zod copies throughout the resolved tree."""
    lock = json.loads((ROOT / "integrations/dsh/package-lock.json").read_text(encoding="utf-8"))
    seen = {"undici": [], "zod": []}
    for path, package in lock["packages"].items():
        for name, floor, advisory in (
            ("undici", (8, 12, 2), "GHSA-xjj6-f33q-929c"),
            ("zod", (4, 6, 6), "GHSA-mrhx-c7xc-m3w5"),
        ):
            if path.endswith(f"node_modules/{name}"):
                assert at_least(package["version"], floor), f"{path} retains {advisory}"
                seen[name].append(path)
    assert seen["undici"], "The resolved HTTP client must be audited"
    assert seen["zod"], "The resolved schema validator must be audited"


def test_dsh_lock_excludes_vulnerable_zip_parser_versions():
    """Reject every affected fflate copy, including the Office dependency."""
    lock = json.loads((ROOT / "integrations/dsh/package-lock.json").read_text(encoding="utf-8"))
    copies = []
    for path, package in lock["packages"].items():
        if path.endswith("node_modules/fflate"):
            assert at_least(package["version"], (0, 8, 3)), f"{path} retains GHSA-px8p-9vwx-vf98"
            copies.append(path)
    assert copies, "The actual DSH Office ZIP dependency must be audited"
