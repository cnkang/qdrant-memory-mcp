"""Lock builder prototype: unit coverage for its orchestration and contracts."""

import hashlib
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


def pinned_meta(wheel, sha="a" * 64):
    release = current_release()
    return {
        "wheel": wheel,
        "sha256": sha,
        "commit": release["runtime_commit"],
        "runtime_version": release["runtime_version"],
    }


def current_release():
    return json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )


def runtime_wheel_name():
    return (
        "hermes_plugin_qdrant_memory-"
        + current_release()["runtime_version"]
        + "-py3-none-any.whl"
    )


def wheel_meta(wheel):
    return pinned_meta(wheel.name, hashlib.sha256(wheel.read_bytes()).hexdigest())


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
        module.run("git", ["fetch", "--upload-pack=/tmp/evil"], work)


@pytest.mark.parametrize(
    "executable",
    ["sh", "./git", "/bin/sh", "/tmp/venv/bin/rm", "/tmp/attacker/python", "", 42],
)
def test_run_rejects_unapproved_executables(work, monkeypatch, executable):
    module = load_locks()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "unapproved executable reached subprocess"
        ),
    )

    with pytest.raises(ValueError):
        module.run(executable, ["--version"], work)


def test_run_accepts_a_local_interpreter_under_the_temp_root(work, monkeypatch):
    module = load_locks()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    builder = work / "qm-lock-verify-test"
    python = builder / "venv" / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    python.parent.mkdir(parents=True)

    module.run(str(python), ["--help"], work)

    assert calls == [[str(python.resolve()), "--help"]]


def test_run_accepts_a_symlinked_venv_interpreter(work, monkeypatch):
    module = load_locks()
    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv)
        or types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    builder = work / "qm-lock-verify-test"
    base = work / "base-python"
    base.write_text("")
    python = builder / "venv" / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    python.parent.mkdir(parents=True)
    if sys.platform == "win32":
        # Windows venv interpreters are copies; symlinks need a privilege.
        python.write_text("")
    else:
        python.symlink_to(base)

    module.run(str(python), ["--help"], work)

    assert calls == [[str(python), "--help"]]


def test_run_rejects_executables_outside_the_run_root(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("unapproved executable reached subprocess"),
    )
    attacker = work.parent / "attacker" / "python"

    with pytest.raises(ValueError, match="not an approved command"):
        module.run(str(attacker), ["--help"], work)

    lookalike = work.parent / "qm-lock-attacker" / "python"
    with pytest.raises(ValueError, match="not an approved command"):
        module.run(str(lookalike), ["--help"], work)


def test_run_allows_approved_options_and_paths_with_spaces(work, monkeypatch):
    module = load_locks()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    output_dir = work / "wheel output"
    arguments = [
        "build",
        "--no-header",
        "--wheel",
        "--out-dir",
        str(output_dir),
        str(work),
    ]

    result = module.run("uv", arguments, work)

    assert result.returncode == 0
    assert calls == [
        (
            ["uv", *arguments],
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
    commit = current_release()["runtime_commit"]
    source.write_text(
        "annotated-types==0.8.0 \\\n    --hash=sha256:aa\n"
        "hermes-plugin-qdrant-memory @ git+https://github.com/cnkang/"
        f"hermes-plugin-qdrant-memory.git@{commit}\n"
        "qdrant-memory-mcp==0.3.3 \\\n    --hash=sha256:bb\n",
        encoding="utf-8",
    )
    filtered = module.hashed_requirements("macos-arm64", work)
    text = filtered.read_text(encoding="utf-8")
    assert "git+" not in text
    assert "annotated-types==0.8.0" in text
    assert "qdrant-memory-mcp==0.3.3" in text
    assert "hermes-plugin-qdrant-memory" not in text


def test_hashed_requirements_reject_unlisted_platform(work):
    module = load_locks()
    with pytest.raises(ValueError, match="Unsupported runtime lock platform"):
        module.hashed_requirements("../outside", work)


@pytest.mark.parametrize("commit", ["-help", "a" * 39, "g" * 40, "a" * 40 + "--"])
def test_validate_runtime_commit_rejects_non_object_ids(commit):
    module = load_locks()
    with pytest.raises(ValueError, match="full lowercase 40-character Git SHA"):
        module.validate_runtime_commit(commit)


@pytest.mark.parametrize(
    "name",
    ["../evil.whl", "/tmp/evil.whl", "dir/evil.whl", "wheel.txt", "", 7],
)
def test_validate_runtime_wheel_rejects_paths_and_other_files(name):
    module = load_locks()
    with pytest.raises(ValueError, match="plain .whl filename"):
        module.validate_runtime_wheel(name)


def test_validate_runtime_wheel_accepts_a_builder_wheel_name():
    module = load_locks()
    name = runtime_wheel_name()
    assert module.validate_runtime_wheel(name) == name


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "g" * 64, "", 5])
def test_validate_sha256_rejects_non_lowercase_hex(digest):
    module = load_locks()
    with pytest.raises(ValueError, match="64 lowercase hex"):
        module.validate_sha256(digest)


def test_verify_offline_rejects_an_unknown_platform(work):
    module = load_locks()
    with pytest.raises(ValueError, match="Unsupported runtime lock platform"):
        module.verify_offline("../outside", work, {})


def test_validate_runtime_commit_accepts_full_object_id():
    module = load_locks()
    commit = "a" * 40
    assert module.validate_runtime_commit(commit) == commit


def test_offline_requirements_substitute_the_recorded_wheel(work, monkeypatch):
    module = load_locks()
    lock_dir = work / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(module, "LOCKS", lock_dir)
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"wheel-bytes")
    meta = wheel_meta(wheel)
    commit = current_release()["runtime_commit"]
    (lock_dir / "macos-arm64.txt").write_text(
        "annotated-types==0.8.0\n"
        "hermes-plugin-qdrant-memory @ git+https://github.com/cnkang/"
        f"hermes-plugin-qdrant-memory.git@{commit}\n",
        encoding="utf-8",
    )
    target = module.offline_requirements("macos-arm64", wheelhouse, meta, work)
    text = target.read_text(encoding="utf-8")
    assert wheel.resolve().as_uri() in text
    assert f"--hash=sha256:{meta['sha256']}" in text
    assert "git+" not in text


def test_offline_requirements_substitute_public_runtime_wheel_hash_block(work, monkeypatch):
    module = load_locks()
    lock_dir = work / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(module, "LOCKS", lock_dir)
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"source-built-runtime")
    meta = wheel_meta(wheel)
    runtime_version = current_release()["runtime_version"]
    source = lock_dir / "macos-arm64.txt"
    source.write_text(
        "annotated-types==0.8.0 \\\n    --hash=sha256:aa\n"
        f"hermes-plugin-qdrant-memory=={runtime_version} \\\n"
        "    --hash=sha256:public-pypi-wheel-hash\n"
        "qdrant-memory-mcp==0.3.3 \\\n    --hash=sha256:bb\n",
        encoding="utf-8",
    )
    target = module.offline_requirements("macos-arm64", wheelhouse, meta, work)
    text = target.read_text(encoding="utf-8")
    assert wheel.resolve().as_uri() in text
    assert f"--hash=sha256:{meta['sha256']}" in text
    assert "public-pypi-wheel-hash" not in text
    assert "annotated-types==0.8.0" in text
    assert "qdrant-memory-mcp==0.3.3" in text
    assert text.count("file://") == 1


def test_offline_requirements_reject_runtime_wheel_hash_mismatch(work, monkeypatch):
    module = load_locks()
    lock_dir = work / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(module, "LOCKS", lock_dir)
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"source-built-runtime")
    meta = wheel_meta(wheel)
    meta["sha256"] = "a" * 64
    commit = current_release()["runtime_commit"]
    (lock_dir / "macos-arm64.txt").write_text(
        "hermes-plugin-qdrant-memory @ git+https://github.com/cnkang/"
        f"hermes-plugin-qdrant-memory.git@{commit}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SHA-256 does not match"):
        module.offline_requirements("macos-arm64", wheelhouse, meta, work)


@pytest.mark.parametrize(
    "runtime_entries",
    [
        "annotated-types==0.8.0\n",
        "hermes-plugin-qdrant-memory @ git+https://github.com/cnkang/"
        "hermes-plugin-qdrant-memory.git@{commit}\n"
        "hermes-plugin-qdrant-memory @ git+https://github.com/cnkang/"
        "hermes-plugin-qdrant-memory.git@{commit}\n",
    ],
)
def test_offline_requirements_require_exactly_one_runtime_substitution(
    work, monkeypatch, runtime_entries
):
    module = load_locks()
    lock_dir = work / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(module, "LOCKS", lock_dir)
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"source-built-runtime")
    meta = wheel_meta(wheel)
    commit = current_release()["runtime_commit"]
    source = lock_dir / "macos-arm64.txt"
    source.write_text(runtime_entries.format(commit=commit), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one Runtime requirement"):
        module.offline_requirements("macos-arm64", wheelhouse, meta, work)


def test_compile_lock_uses_expected_flags(work, monkeypatch):
    module = load_locks()
    argv_seen = []
    requirement_inputs = []
    lock_dir = work / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(module, "LOCKS", lock_dir)

    def fake_run(executable, arguments, cwd, **kwargs):
        argv_seen.append([executable, *arguments])
        requirement_path = next(
            Path(argument)
            for argument in arguments
            if argument.endswith("desktop-runtime-lock-requirements.txt")
        )
        requirement_inputs.append(requirement_path.read_text(encoding="utf-8"))
        output_path = Path(arguments[arguments.index("-o") + 1])
        output_path.write_text(
            "qdrant-memory-mcp==0.3.3\n"
            f"    # via -r {requirement_path}\n",
            encoding="utf-8",
        )
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    output = module.compile_lock("windows-x64", work)
    assert output == lock_dir / "windows-x64.txt"
    args = argv_seen[0]
    assert "--python-platform" in args
    assert "x86_64-pc-windows-msvc" in args
    assert "--generate-hashes" in args
    assert "--no-header" in args
    assert args[args.index("-o") + 1] == str(output)
    release = current_release()
    assert "qdrant-memory-mcp==0.3.3" in requirement_inputs[0]
    assert (
        f"hermes-plugin-qdrant-memory[mcp,local] @ git+"
        f"{module.RUNTIME_REPOSITORY}@{release['runtime_commit']}"
    ) in requirement_inputs[0]
    assert "hermes-plugin-qdrant-memory[mcp,local]==" not in requirement_inputs[0]
    generated = output.read_text(encoding="utf-8")
    assert generated.startswith(
        "# Generated by scripts/build_runtime_locks.py; do not edit.\n"
        "# Source requirements: plugins/qdrant-memory/requirements.txt\n"
        "# Target: windows-x64 (x86_64-pc-windows-msvc; Python 3.11)\n"
        f"# Runtime source commit: {release['runtime_commit']}\n\n"
    )
    assert str(work) not in generated
    assert "# via -r plugins/qdrant-memory/requirements.txt" in generated


def test_compile_lock_surfaces_resolution_failures(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(
        module, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(RuntimeError, match="boom"):
        module.compile_lock("linux-x64", work)


def test_compile_lock_rejects_runtime_requirement_version_drift(work, monkeypatch):
    module = load_locks()
    requirements = work / "requirements.txt"
    requirements.write_text(
        "qdrant-memory-mcp==0.3.3\n"
        "hermes-plugin-qdrant-memory[mcp,local]==0.6.1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REQUIREMENTS", requirements)
    with pytest.raises(ValueError, match="Runtime version must match release.json"):
        module._runtime_requirement_for_desktop_lock(work)


def test_build_runtime_wheel_records_hash_and_save(work, monkeypatch):
    module = load_locks()
    created = []

    def fake_run(executable, arguments, cwd, **kwargs):
        if executable == "git" and arguments[-2:] == ["rev-parse", "HEAD"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=current_release()["runtime_commit"] + "\n",
                stderr="",
            )
        if executable == "uv" and arguments[:1] == ["build"]:
            wheel_dir = cwd / "wheel"
            wheel_dir.mkdir(parents=True, exist_ok=True)
            target = wheel_dir / runtime_wheel_name()
            target.write_bytes(b"wheel-bytes")
        created.append((executable, arguments[:1]))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    meta = module.build_runtime_wheel(work, save_dir=work / "saved")
    assert created[0] == ("git", ["init"])
    assert ("git", ["-C"]) in created
    assert ("uv", ["build"]) in created
    assert meta["sha256"] == __import__("hashlib").sha256(b"wheel-bytes").hexdigest()
    assert meta["commit"] == json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )["runtime_commit"]
    assert (work / "saved/runtime-wheel.json").is_file()
    assert (work / "saved" / meta["wheel"]).is_file()
    recorded = json.loads((work / "saved/runtime-wheel.json").read_text(encoding="utf-8"))
    assert recorded == meta


def test_build_runtime_wheel_refuses_to_overwrite_a_different_same_name_wheel(
    work, monkeypatch
):
    module = load_locks()
    save_dir = work / "wheelhouse"
    save_dir.mkdir()
    existing = save_dir / runtime_wheel_name()
    existing.write_bytes(b"public-pypi-wheel")

    def fake_run(executable, arguments, cwd, **kwargs):
        if executable == "git" and arguments[-2:] == ["rev-parse", "HEAD"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=current_release()["runtime_commit"] + "\n",
                stderr="",
            )
        if executable == "uv" and arguments[:1] == ["build"]:
            wheel_dir = cwd / "wheel"
            wheel_dir.mkdir(parents=True, exist_ok=True)
            (wheel_dir / runtime_wheel_name()).write_bytes(b"source-wheel")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module.build_runtime_wheel(work, save_dir=save_dir)
    assert existing.read_bytes() == b"public-pypi-wheel"
    assert not (save_dir / "runtime-wheel.json").exists()


def test_build_runtime_wheel_fails_on_build_error(work, monkeypatch):
    module = load_locks()

    def fake_run(executable, arguments, cwd, **kwargs):
        if executable == "git" and arguments[-2:] == ["rev-parse", "HEAD"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=current_release()["runtime_commit"] + "\n",
                stderr="",
            )
        if executable == "uv" and arguments[:1] == ["build"]:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="wheel boom")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    with pytest.raises(RuntimeError, match="wheel boom"):
        module.build_runtime_wheel(work)


def test_build_runtime_wheel_requires_the_wheel(work, monkeypatch):
    module = load_locks()
    def fake_run(executable, arguments, cwd, **kwargs):
        if executable == "git" and arguments[-2:] == ["rev-parse", "HEAD"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=current_release()["runtime_commit"] + "\n",
                stderr="",
            )
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    with pytest.raises(RuntimeError, match="exactly one wheel"):
        _ = module.build_runtime_wheel(work)


def test_verify_offline_hashes_wheels_and_probes_console(work, monkeypatch):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    runtime_wheel = wheelhouse / runtime_wheel_name()
    runtime_wheel.write_bytes(b"wheel")
    meta = wheel_meta(runtime_wheel)
    lockfile = module.LOCKS / "macos-arm64.txt"
    assert lockfile.is_file()
    steps = {"install": 0}
    install_calls = []

    def fake_run(executable, arguments, cwd, **kwargs):
        if arguments[:3] == ["-P", "-m", "pip"]:
            steps["install"] += 1
            install_calls.append((arguments, cwd))
            return types.SimpleNamespace(returncode=0, stdout="Installed", stderr="")
        if arguments == ["--help"]:
            return types.SimpleNamespace(returncode=0, stdout="runtime help", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    result = module.verify_offline("macos-arm64", wheelhouse, meta)
    assert result == {
        "target": "macos-arm64", "installed": True, "offline": True,
        "require_hashes": True, "console_probe": True,
    }
    assert steps["install"] == 1
    arguments, cwd = install_calls[0]
    assert cwd == wheelhouse
    assert arguments[:3] == ["-P", "-m", "pip"]
    assert str(wheelhouse) not in arguments
    requirements = Path(arguments[arguments.index("-r") + 1])
    assert requirements.is_absolute()
    assert requirements.parent.name.startswith("qm-lock-verify-")
    assert wheelhouse not in requirements.parents
    assert requirements.name == module.VERIFY_REQUIREMENTS_FILENAME
    assert arguments[arguments.index("--find-links") + 1] == "."


def test_verify_offline_rejects_a_mismatched_host_architecture(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")

    with pytest.raises(RuntimeError, match="requires host architecture arm64"):
        module.verify_offline("macos-arm64", work, {})


def test_verify_offline_rejects_stale_wheelhouse_metadata(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    meta = {
        "wheel": runtime_wheel_name(),
        "sha256": "a" * 64,
        "commit": "b" * 40,
        "runtime_version": current_release()["runtime_version"],
    }

    with pytest.raises(ValueError, match="does not match the pinned release"):
        module.verify_offline("macos-arm64", work, meta)


def test_verify_offline_fails_when_the_console_probe_fails(work, monkeypatch):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"w")

    def fake_subprocess(argv, **kwargs):
        if argv[-1] == "--help":
            return types.SimpleNamespace(returncode=2, stdout="", stderr="broken")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_subprocess)
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    meta = wheel_meta(wheel)
    with pytest.raises(RuntimeError, match="broken"):
        module.verify_offline("macos-arm64", wheelhouse, meta)


def test_verify_offline_uses_a_private_requirements_file_per_run(work, monkeypatch):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"w")
    meta = wheel_meta(wheel)
    requirements_paths = []
    venv_arguments = []

    def fake_run(executable, arguments, cwd, **kwargs):
        if arguments[:1] == ["venv"]:
            venv_arguments.append(list(arguments))
        if arguments[:3] == ["-P", "-m", "pip"]:
            requirements_paths.append(arguments[arguments.index("-r") + 1])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    module.verify_offline("macos-arm64", wheelhouse, meta)
    module.verify_offline("macos-arm64", wheelhouse, meta)

    assert len(requirements_paths) == 2
    assert len(venv_arguments) == 2
    for arguments in venv_arguments:
        assert "--offline" in arguments
        assert "--no-python-downloads" in arguments
    assert requirements_paths[0] != requirements_paths[1]
    for candidate in requirements_paths:
        path = Path(candidate)
        assert path.is_absolute()
        assert path.parent != wheelhouse
        assert wheelhouse not in path.parents


def test_verify_offline_fails_when_install_fails(work, monkeypatch):
    module = load_locks()
    wheelhouse = work / "wh"
    wheelhouse.mkdir()
    wheel = wheelhouse / runtime_wheel_name()
    wheel.write_bytes(b"w")
    meta = wheel_meta(wheel)

    def fake_run(executable, arguments, cwd, **kwargs):
        if arguments[:3] == ["-P", "-m", "pip"]:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="hash check failed")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    with pytest.raises(RuntimeError, match="hash check failed"):
        module.verify_offline("macos-arm64", wheelhouse, meta)


def test_seeded_python_uses_uv_venv(work, monkeypatch):
    module = load_locks()
    seen = []

    def fake_run(executable, arguments, cwd, **kwargs):
        seen.append((executable, arguments[0]))
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
    downloaded_requirements = []
    wheelbuilt = {"done": False}

    def fake_run(executable, arguments, cwd, **kwargs):
        if arguments[:3] == ["-P", "-m", "pip"]:
            pip_calls.append(([executable, *arguments], cwd))
            requirement_path = Path(arguments[arguments.index("-r") + 1])
            downloaded_requirements.append(
                requirement_path.read_text(encoding="utf-8")
            )
            wheelhouse_flag = arguments[arguments.index("-d") + 1]
            destination = cwd if wheelhouse_flag == "." else Path(wheelhouse_flag)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "annotated_types-0.8.0-py3-none-any.whl").write_bytes(b"w")
        if executable == "git" and arguments[-2:] == ["rev-parse", "HEAD"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=current_release()["runtime_commit"] + "\n",
                stderr="",
            )
        if executable == "uv" and arguments[:1] == ["build"]:
            wheel_dir = cwd / "wheel"
            wheel_dir.mkdir(parents=True, exist_ok=True)
            (wheel_dir / runtime_wheel_name()).write_bytes(b"w")
            wheelbuilt["done"] = True
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    wheelhouse = module.build_wheelhouse(work / "house")
    assert wheelbuilt["done"]
    assert (wheelhouse / "runtime-wheel.json").is_file()
    expected_targets = module.host_platforms()
    assert pip_calls, "pip download must run for each host platform lock"
    assert all(
        not any(
            module._requirement_name(line) == module.RUNTIME_DISTRIBUTION
            for line in text.splitlines()
        )
        for text in downloaded_requirements
    )
    assert all("qdrant-memory-mcp==0.3.3" in text for text in downloaded_requirements)
    assert (wheelhouse / runtime_wheel_name()).is_file()
    metadata = json.loads((wheelhouse / "runtime-wheel.json").read_text(encoding="utf-8"))
    assert metadata["sha256"] == hashlib.sha256(
        (wheelhouse / runtime_wheel_name()).read_bytes()
    ).hexdigest()
    download_arguments, download_cwd = pip_calls[0]
    assert download_cwd == wheelhouse
    assert download_arguments[1:4] == ["-P", "-m", "pip"]
    assert str(wheelhouse.resolve()) not in download_arguments
    assert download_arguments[download_arguments.index("-d") + 1] == "."
    for platform in expected_targets:
        assert any(
            f"hashed-{platform}" in " ".join(arguments)
            for arguments, _cwd in pip_calls
        )


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
    readme = (sandbox_locks / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Runtime")
    assert "not committed here" in readme
    assert "gated on the host architecture" in readme


def test_main_verify_requires_existing_wheelhouse(work, monkeypatch):
    module = load_locks()
    monkeypatch.setattr("sys.argv", ["locks", "--verify", "macos-arm64", "--wheelhouse", str(work / "absent")])
    with pytest.raises(SystemExit):
        module.main()


def test_locks_directory_lives_outside_the_plugin_package():
    module = load_locks()
    assert module.LOCKS == ROOT / "runtime-locks"
    assert not (ROOT / "plugins/qdrant-memory/runtime-locks").exists()
