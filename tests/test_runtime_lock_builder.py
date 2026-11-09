"""Lock builder prototype: unit coverage for its orchestration and contracts."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_locks():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_locks", ROOT / "scripts/build_runtime_locks.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_runtime_locks"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def work(tmp_path):
    return tmp_path


def test_platform_matrix_is_complete():
    module = load_locks()
    assert sorted(module.PLATFORM_LOCKS) == [
        "linux-x64", "macos-arm64", "macos-x64", "windows-x64",
    ]
    windows = module.PLATFORM_LOCKS["windows-x64"]
    assert windows == ("x86_64-pc-windows-msvc", "3.11")
    arm = module.PLATFORM_LOCKS["macos-arm64"]
    assert arm == ("aarch64-apple-darwin", "3.11")


def test_run_rejects_unapproved_option_arguments(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("unsafe arguments reached subprocess"),
    )

    with pytest.raises(ValueError, match="unapproved option"):
        module.run(["git", "fetch", "--upload-pack=/tmp/evil"], work)


def test_run_allows_approved_options_and_paths_with_spaces(work, monkeypatch):
    module = load_locks()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    output_dir = work / "wheel output"
    command = ["uv", "build", "--wheel", "--out-dir", str(output_dir), str(work)]

    result = module.run(command, work)

    assert result.returncode == 0
    assert calls == [
        (
            command,
            {"cwd": work, "capture_output": True, "text": True},
        )
    ]


def test_host_platforms_follow_the_host(monkeypatch):
    module = load_locks()
    for platform, expected in (
        ("darwin", ["macos-arm64", "macos-x64"]),
        ("win32", ["windows-x64"]),
        ("linux", ["linux-x64"]),
    ):
        monkeypatch.setattr(sys, "platform", platform)
        assert module.host_platforms() == expected


def test_hashed_requirements_drop_the_git_runtime_line(work, monkeypatch):
    module = load_locks()
    lock_dir = work / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(module, "LOCKS", lock_dir)
    source = lock_dir / "macos-arm64.txt"
    source.write_text(
        "annotated-types==0.8.0 \\\n    --hash=sha256:aa\n"
        "hermes-plugin-qdrant-memory @ git+https://github.com/cnkang/"
        "hermes-plugin-qdrant-memory.git@dee6777432f17523db75f6be32cf3ef15e48235c\n"
        "qdrant-memory-mcp==0.3.1 \\\n    --hash=sha256:bb\n",
        encoding="utf-8",
    )
    filtered = module.hashed_requirements("macos-arm64", work)
    text = filtered.read_text(encoding="utf-8")
    assert "git+" not in text
    assert "annotated-types==0.8.0" in text
    assert "qdrant-memory-mcp==0.3.1" in text


def test_hashed_requirements_reject_unlisted_platform(work):
    module = load_locks()
    with pytest.raises(ValueError, match="Unsupported runtime lock platform"):
        module.hashed_requirements("../outside", work)


@pytest.mark.parametrize("commit", ["-help", "a" * 39, "g" * 40, "a" * 40 + "--"])
def test_validate_runtime_commit_rejects_non_object_ids(commit):
    module = load_locks()
    with pytest.raises(ValueError, match="full lowercase 40-character Git SHA"):
        module.validate_runtime_commit(commit)


def test_validate_runtime_commit_accepts_full_object_id():
    module = load_locks()
    commit = "a" * 40
    assert module.validate_runtime_commit(commit) == commit


def test_offline_requirements_substitute_the_recorded_wheel(work):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes")
    meta = {
        "wheel": wheel.name,
        "sha256": "a" * 64,
        "commit": "d" * 40,
        "runtime_version": "0.6.0",
    }
    lock = work / "macos-arm64.txt"
    lock.write_text(
        "annotated-types==0.8.0\n"
        "hermes-plugin-qdrant-memory @ git+https://github.com/x@dee6777432f17523db75f6be32cf3ef15e48235c\n",
        encoding="utf-8",
    )
    target = module.offline_requirements(lock, wheelhouse, meta)
    text = target.read_text(encoding="utf-8")
    assert wheel.resolve().as_uri() in text
    assert f"--hash=sha256:{'a' * 64}" in text
    assert "git+" not in text


def test_offline_requirements_require_exact_one_substitution(work):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    (wheelhouse / "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl").write_bytes(b"x")
    meta = {"wheel": "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl",
            "sha256": "b" * 64, "commit": "c" * 40, "runtime_version": "0.6.0"}
    source = work / "l.txt"
    source.write_text("annotated-types==0.8.0\n"
                      "hermes-plugin-qdrant-memory @ git+https://x@dee6777432f17523db75f6be32cf3ef15e48235c\n"
                      "qdrant-memory-mcp==0.3.1\n", encoding="utf-8")
    target = module.offline_requirements(source, wheelhouse, meta)
    subs = [line for line in target.read_text(encoding="utf-8").splitlines() if "file://" in line]
    assert len(subs) == 1


def test_compile_lock_uses_expected_flags(work, monkeypatch):
    module = load_locks()
    argv_seen = []

    def fake_run(argv, cwd, **kwargs):
        argv_seen.append(list(argv))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    output = module.compile_lock("windows-x64", work)
    assert output == module.LOCKS / "windows-x64.txt"
    args = argv_seen[0]
    assert "--python-platform" in args
    assert "x86_64-pc-windows-msvc" in args
    assert "--generate-hashes" in args
    assert args[args.index("-o") + 1].startswith("runtime-locks/")
    assert "plugins/qdrant-memory/requirements.txt" in args


def test_compile_lock_surfaces_resolution_failures(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(
        module, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(RuntimeError, match="boom"):
        module.compile_lock("linux-x64", work)


def test_build_runtime_wheel_records_hash_and_save(work, monkeypatch):
    module = load_locks()
    created = []

    def fake_run(argv, cwd, **kwargs):
        if argv[:2] == ["uv", "build"]:
            wheel_dir = cwd / "wheel"
            wheel_dir.mkdir(parents=True, exist_ok=True)
            target = wheel_dir / "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl"
            target.write_bytes(b"wheel-bytes")
        created.append(argv[:2])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    meta = module.build_runtime_wheel(work, save_dir=work / "saved")
    assert created[0][:2] == ["git", "init"]
    assert ["git", "-C"] in created
    assert ["uv", "build"] in created
    assert meta["sha256"] == __import__("hashlib").sha256(b"wheel-bytes").hexdigest()
    assert meta["commit"] == json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )["runtime_commit"]
    assert (work / "saved/runtime-wheel.json").is_file()
    assert (work / "saved" / meta["wheel"]).is_file()
    recorded = json.loads((work / "saved/runtime-wheel.json").read_text(encoding="utf-8"))
    assert recorded == meta


def test_build_runtime_wheel_fails_on_build_error(work, monkeypatch):
    module = load_locks()

    def fake_run(argv, cwd, **kwargs):
        if argv[:2] == ["uv", "build"]:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="wheel boom")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    with pytest.raises(RuntimeError, match="wheel boom"):
        module.build_runtime_wheel(work)


def test_build_runtime_wheel_requires_the_wheel(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(
        module, "run", lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    with pytest.raises(StopIteration):
        _ = module.build_runtime_wheel(work)


def test_verify_offline_hashes_wheels_and_probes_console(work, monkeypatch):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    runtime_wheel = wheelhouse / "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl"
    runtime_wheel.write_bytes(b"wheel")
    meta = {"wheel": runtime_wheel.name, "sha256": "c" * 64,
            "commit": "d" * 40, "runtime_version": "0.6.0"}
    lockfile = module.LOCKS / "macos-arm64.txt"
    assert lockfile.is_file()
    steps = {"install": 0}

    def fake_run(argv, cwd, **kwargs):
        if argv[1:3] == ["m", "pip"] or "pip" in argv:
            steps["install"] += 1
            return types.SimpleNamespace(returncode=0, stdout="Installed", stderr="")
        if argv[-1] == "--help":
            return types.SimpleNamespace(returncode=0, stdout="runtime help", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    result = module.verify_offline("macos-arm64", wheelhouse, meta)
    assert result == {
        "target": "macos-arm64", "installed": True, "offline": True,
        "require_hashes": True, "console_probe": True,
    }
    assert steps["install"] == 1


def test_verify_offline_fails_when_install_fails(work, monkeypatch):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    (wheelhouse / "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl").write_bytes(b"w")
    meta = {"wheel": "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl",
            "sha256": "e" * 64, "commit": "f" * 40, "runtime_version": "0.6.0"}
    call = {"n": 0}

    def fake_run(argv, cwd, **kwargs):
        call["n"] += 1
        if call["n"] == 2:  # the pip install step after uv venv
            return types.SimpleNamespace(returncode=1, stdout="", stderr="hash check failed")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    with pytest.raises(RuntimeError, match="hash check failed"):
        module.verify_offline("macos-arm64", wheelhouse, meta)


def test_seeded_python_uses_uv_venv(work, monkeypatch):
    module = load_locks()
    seen = []

    def fake_run(argv, cwd, **kwargs):
        seen.append(tuple(argv[:2]))
        env_dir = cwd / "pip-venv"
        (env_dir / ("Scripts" if sys.platform == "win32" else "bin")).mkdir(
            parents=True, exist_ok=True
        )
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    python = module.seeded_python(work)
    assert ("uv", "venv") in seen
    assert python.name in {"python.exe", "python"}


def test_build_wheelhouse_downloads_for_host_and_saves_wheel(work, monkeypatch):
    module = load_locks()
    pip_calls = []
    wheelbuilt = {"done": False}

    def fake_run(argv, cwd, **kwargs):
        if "pip" in argv:
            pip_calls.append([str(item) for item in argv])
            wheelhouse_flag = argv[argv.index("-d") + 1]
            destination = Path(wheelhouse_flag)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "annotated_types-0.8.0-py3-none-any.whl").write_bytes(b"w")
        if argv[:2] == ["uv", "build"]:
            wheel_dir = cwd / "wheel"
            wheel_dir.mkdir(parents=True, exist_ok=True)
            (wheel_dir / "hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl").write_bytes(b"w")
            wheelbuilt["done"] = True
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    wheelhouse = module.build_wheelhouse(work / "house")
    assert wheelbuilt["done"]
    assert (wheelhouse / "runtime-wheel.json").is_file()
    expected_targets = module.host_platforms()
    assert pip_calls, "pip download must run for each host platform lock"
    source_flags = [line for line in pip_calls[0] if line.endswith("requirements.txt")]
    _ = source_flags  # the lock is filtered per host platform
    for platform in expected_targets:
        assert any(f"hashed-{platform}" in " ".join(call) for call in pip_calls)


def test_main_routes_by_flags(work, monkeypatch, tmp_path):
    module = load_locks()
    routed = {"verify": 0, "wheelhouse": 0, "locks": 0}
    # Keep generated artifacts away from the real repository lock directory.
    sandbox_locks = tmp_path / "locks"
    sandbox_locks.mkdir()
    monkeypatch.setattr(module, "LOCKS", sandbox_locks)

    monkeypatch.setattr(
        module, "verify_offline", lambda *a, **k: routed.update(verify=1) or {"target": "x"}
    )
    monkeypatch.setattr(
        module, "build_wheelhouse", lambda path: routed.update(wheelhouse=1) or path
    )
    monkeypatch.setattr(
        module,
        "build_runtime_wheel",
        lambda w, save_dir=None: routed.update(locks=1)
        or {"wheel": "w", "sha256": "z", "commit": "c", "runtime_version": "0"},
    )
    monkeypatch.setattr(module, "compile_lock", lambda *a, **k: None)
    house = work / "house"
    house.mkdir()
    (house / "runtime-wheel.json").write_text(
        json.dumps({"wheel": "w", "sha256": "z", "commit": "c", "runtime_version": "0"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["locks", "--verify", "macos-arm64", "--wheelhouse", str(house)])
    module.main()
    assert routed["verify"] == 1
    monkeypatch.setattr("sys.argv", ["locks", "--wheelhouse", str(work / "new-house")])
    module.main()
    assert routed["wheelhouse"] == 1
    monkeypatch.setattr("sys.argv", ["locks"])
    module.main()
    assert routed["locks"] == 1
    assert (sandbox_locks / "README.md").read_text(encoding="utf-8").startswith("# Runtime")


def test_main_verify_requires_existing_wheelhouse(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr("sys.argv", ["locks", "--verify", "macos-arm64", "--wheelhouse", str(work / "absent")])
    with pytest.raises(SystemExit):
        module.main()


def test_locks_directory_lives_outside_the_plugin_package():
    module = load_locks()
    assert module.LOCKS == ROOT / "runtime-locks"
    assert not (ROOT / "plugins/qdrant-memory/runtime-locks").exists()
