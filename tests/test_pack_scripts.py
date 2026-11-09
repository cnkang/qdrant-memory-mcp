"""The npm pack steps keep their output policy and identity checks."""

import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = {
    "pack_launcher": {
        "source": ROOT / "integrations/managed",
        "output": "dist/launcher",
        "executable": "launcher.mjs",
    },
    "pack_dsh_bundle": {
        "source": ROOT / "integrations/dsh/bundle",
        "output": "dist/dsh-bundle",
        "executable": None,
    },
}


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_archive(destination, module, source, executable):
    """Write the payload npm would have produced, from the reviewed source."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as package:
        for name in sorted(module.FILES):
            path = module.payload_path(source, name) if hasattr(module, 'payload_path') else source / name
            data = path.read_bytes()
            member = tarfile.TarInfo("package/" + name)
            member.mode = 0o755 if name == executable else 0o644
            member.size = len(data)
            package.addfile(member, io.BytesIO(data))


def prepare_launcher_pin(tmp_path, module, source):
    repo_root = tmp_path / "repo"
    managed_source = repo_root / "integrations" / "managed"
    managed_source.parent.mkdir(parents=True)
    managed_source.symlink_to(source, target_is_directory=True)
    fixture_archive = tmp_path / "launcher-fixture.tgz"
    write_archive(fixture_archive, module, source, "launcher.mjs")
    integrity = module.sha512_integrity(fixture_archive)
    (repo_root / "launcher-source.json").write_text(
        json.dumps({"integrity": integrity}), encoding="utf-8")
    return fixture_archive, integrity, repo_root


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_normalize_accepts_both_npm_report_shapes(name):
    module = load(name)
    packed = {"filename": "x.tgz", "integrity": "sha512-abc"}
    assert module.normalize([packed]) == packed
    assert module.normalize({"x": packed}) == packed


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_normalize_rejects_an_unknown_report_shape(name):
    module = load(name)
    with pytest.raises(ValueError):
        module.normalize({"a": {"filename": "x.tgz"}, "b": {"filename": "y.tgz"}})
    with pytest.raises(ValueError):
        module.normalize({"a": "not-a-report"})


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_main_packs_once_into_an_external_directory(name, tmp_path, monkeypatch, capsys):
    script = SCRIPTS[name]
    module = load(name)
    source = script["source"]
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    integrity = "sha512-abc"
    fixture_archive = None
    if name == "pack_launcher":
        fixture_archive, integrity, repo_root = prepare_launcher_pin(tmp_path, module, source)
        monkeypatch.setattr(module, "ROOT", repo_root)

    def fake_pack(command, cwd, env, text, timeout):
        assert command[0] in ("npm", "npm.cmd")
        assert "--ignore-scripts" in command
        assert env["npm_config_pack_destination"] == str(tmp_path / "out")
        archive = Path(env["npm_config_pack_destination"]) / filename
        if fixture_archive:
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(fixture_archive.read_bytes())
        else:
            write_archive(archive, module, source, script["executable"])
        return json.dumps([{"filename": filename, "integrity": integrity}])

    monkeypatch.setattr(module.subprocess, "check_output", fake_pack)
    monkeypatch.setattr(sys, "argv", [name + ".py", "--output-dir", str(tmp_path / "out")])
    module.main()

    report = json.loads(capsys.readouterr().out)
    assert report["archive"].endswith(filename)
    assert report["integrity"] == integrity
    assert len(report["sha256"]) == 64
    assert (tmp_path / "out" / filename).is_file()


def test_launcher_pack_rejects_integrity_mismatch(tmp_path, monkeypatch):
    name = "pack_launcher"
    script = SCRIPTS[name]
    module = load(name)
    source = script["source"]
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    archive = tmp_path / "out" / filename
    fixture_archive, pinned_integrity, repo_root = prepare_launcher_pin(tmp_path, module, source)
    wrong_integrity = "sha512-" + "A" * 86 + "=="
    monkeypatch.setattr(module, "ROOT", repo_root)

    def fake_pack(command, cwd, env, text, timeout):
        assert command[0] in ("npm", "npm.cmd")
        assert "--ignore-scripts" in command
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(fixture_archive.read_bytes())
        return json.dumps([{"filename": filename, "integrity": wrong_integrity}])

    monkeypatch.setattr(module.subprocess, "check_output", fake_pack)
    monkeypatch.setattr(sys, "argv", [name + ".py", "--output-dir", str(tmp_path / "out")])
    with pytest.raises(ValueError, match="integrity differs"):
        module.main()

    assert not archive.exists()


def test_launcher_pack_rejects_modified_archive_bytes(tmp_path, monkeypatch):
    name = "pack_launcher"
    script = SCRIPTS[name]
    module = load(name)
    source = script["source"]
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    archive = tmp_path / "out" / filename
    fixture_archive, pinned_integrity, repo_root = prepare_launcher_pin(tmp_path, module, source)
    monkeypatch.setattr(module, "ROOT", repo_root)

    def fake_pack(command, cwd, env, text, timeout):
        assert command[0] in ("npm", "npm.cmd")
        assert "--ignore-scripts" in command
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(fixture_archive.read_bytes() + b"tampered")
        return json.dumps([{"filename": filename, "integrity": pinned_integrity}])

    monkeypatch.setattr(module.subprocess, "check_output", fake_pack)
    monkeypatch.setattr(sys, "argv", [name + ".py", "--output-dir", str(tmp_path / "out")])
    with pytest.raises(ValueError, match="integrity differs"):
        module.main()

    assert not archive.exists()


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_main_refuses_to_replace_a_release_artifact(name, tmp_path, monkeypatch):
    module = load(name)
    source = SCRIPTS[name]["source"]
    meta = json.loads((source / "package.json").read_text(encoding="utf-8"))
    filename = meta["name"].removeprefix("@").replace("/", "-") + "-" + meta["version"] + ".tgz"
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / filename).write_bytes(b"existing")

    monkeypatch.setattr(sys, "argv", [name + ".py", "--output-dir", str(tmp_path / "out")])
    with pytest.raises(ValueError):
        module.main()


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_main_keeps_in_repository_outputs_at_the_reviewed_path(name, tmp_path, monkeypatch):
    module = load(name)
    script = SCRIPTS[name]
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv",
                        [name + ".py", "--output-dir", str(tmp_path / "elsewhere")])
    with pytest.raises(ValueError):
        module.main()

    # The reviewed path inside the repository is the one accepted, and it must be
    # the only one: a symlinked destination is refused before anything is packed.
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / script["output"].split("/")[1]).symlink_to(tmp_path / "target")
    monkeypatch.setattr(sys, "argv",
                        [name + ".py", "--output-dir", str(tmp_path / script["output"])])
    with pytest.raises(ValueError):
        module.main()
