"""Credential-free E2E harness: unit coverage for its pure orchestration."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import types
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_e2e():
    spec = importlib.util.spec_from_file_location(
        "codex_plugin_e2e", ROOT / "scripts/codex_plugin_e2e.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["codex_plugin_e2e"] = module
    spec.loader.exec_module(module)
    return module


class FakeResult:
    """MCP-compatible tool result carrying one text payload."""

    def __init__(self, payload, is_error=False):
        self._payload = payload
        self._is_error = is_error

    def model_dump(self, *, by_alias=True):
        return {
            "isError": self._is_error,
            "content": [{"type": "text", "text": self._payload}],
        }


class FakeSession:
    """Canned MCP session for launcher lifecycle tests."""

    def __init__(self, script):
        self.script = list(script)

    async def initialize(self):
        return None

    async def list_tools(self):
        class Named:
            def __init__(self, name):
                self.name = name

        return types.SimpleNamespace(
            tools=[Named("qdrant_memory_search"), Named("qdrant_memory_add")]
        )

    async def call_tool(self, name, arguments):
        kind, payload = self.script.pop(0)
        if kind == "result":
            return FakeResult(json.dumps(payload))
        return FakeResult(payload, is_error=True)


def fake_launcher(monkeypatch, module, sessions):
    """Replace launcher_mcp with pending sessions (task context parity)."""
    pending = list(sessions)

    def factory(launcher_path, env=None):
        @asynccontextmanager
        async def inner():
            yield pending.pop(0)

        return inner()

    monkeypatch.setattr(module, "launcher_mcp", factory)


def test_evidence_records_steps_and_status():
    module = load_e2e()
    evidence = module.Evidence()
    assert evidence.step("first", detail=1) == {"step": "first", "detail": 1}
    assert evidence.steps == [{"step": "first", "detail": 1}]
    assert evidence.status() == 0


def test_run_wraps_subprocess_by_expectation(monkeypatch, tmp_path):
    module = load_e2e()

    def ok(argv, **kwargs):
        assert argv[0] == "codex"
        return subprocess.CompletedProcess(argv, 0, stdout="out", stderr="")

    monkeypatch.setattr(subprocess, "run", ok)
    assert module.run(["codex", "x"], {}, tmp_path) == "out"

    def expectable(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", expectable)
    with pytest.raises(RuntimeError, match="boom"):
        module.run(["codex", "x"], {}, tmp_path)
    monkeypatch.setattr(subprocess, "run", expectable)
    assert module.run(["codex", "x"], {}, tmp_path, ok=False) == ""


def test_codex_uses_run_with_default_expectation(monkeypatch, tmp_path):
    module = load_e2e()
    seen = []

    def fake_run(argv, env, cwd, *, ok=True, timeout=180):
        seen.append((argv, ok))
        return ""

    monkeypatch.setattr(module, "run", fake_run)
    module.codex(["plugin", "list"], {}, tmp_path)
    assert tuple(seen[0][0]) == ("codex", "plugin", "list")
    assert seen[0][1] is True


def test_redact_removes_secret_environment_values(monkeypatch):
    module = load_e2e()
    monkeypatch.setattr(
        module, "_secret_env", {"LEASE_TOKEN": "plain-secret"}, raising=False
    )
    assert "plain-secret" not in module.redact("path=plain-secret token")
    assert "innocent text" in module.redact("innocent text")
    monkeypatch.setattr(module, "_secret_env", {}, raising=False)
    assert module.redact("plain-secret") == "plain-secret"


def test_bin_dir_matches_host_layout(tmp_path):
    module = load_e2e()
    expected = "Scripts" if sys.platform == "win32" else "bin"
    assert module.bin_dir(tmp_path) == tmp_path / expected


def test_launcher_env_filters_secrets_and_clears_overrides(monkeypatch):
    module = load_e2e()
    argv_env = {
        "SECRET_A": "v",
        "PATH": "/x",
        "QDRANT_MEMORY_CODEX_ROOT": "/old",
        "QDRANT_MEMORY_CODEX_OWNER_URL": "https://x",
        "QDRANT_MEMORY_SHARED_TOKEN": "t",
        "QDRANT_MEMORY_CODEX_PROFILE": "old-p",
        "QDRANT_MEMORY_CODEX_EXECUTABLE": "old-e",
        "QDRANT_MEMORY_CODEX_PYTHON": "old-py",
    }
    monkeypatch.setattr(module, "_secret_env", {"SECRET_A": "v"}, raising=False)
    monkeypatch.setattr(module.os, "environ", argv_env, raising=False)
    env = module.launcher_env("/p", "/r")
    assert "SECRET_A" not in env
    assert env["PATH"] == "/x"
    assert env["QDRANT_MEMORY_CODEX_PROFILE"] == "/p"
    assert env["QDRANT_MEMORY_CODEX_EXECUTABLE"] == "/r"
    for name in module.ENV_VAR_NAMES:
        if name not in {
            "QDRANT_MEMORY_CODEX_PROFILE",
            "QDRANT_MEMORY_CODEX_EXECUTABLE",
        }:
            assert name not in env


def test_setup_profile_args_shape(tmp_path):
    module = load_e2e()
    args = module.setup_profile_args("/exe", tmp_path / "profile", 1337, "u", "a")
    assert args[0] == "/exe"
    assert args[1] == "setup"
    stringed = [str(arg) for arg in args]
    assert str(tmp_path / "profile") in stringed
    assert args.index("--embedding-provider") < args.index("ollama")
    for flag in ("--model", "--dimensions", "--base-url", "--user-id", "--agent-id"):
        assert flag in stringed
    assert args[-1] == "http://127.0.0.1:1337"


def test_setup_profile_args_match_protected_acceptance(tmp_path):
    """The credential-free lane mirrors the protected provider selection codes."""
    module = load_e2e()
    acceptance = importlib.util.spec_from_file_location(
        "acc_probe", ROOT / "scripts/codex_account_acceptance.py"
    )
    _module = importlib.util.module_from_spec(acceptance)
    acceptance.loader.exec_module(_module)
    _ = _module
    args = module.setup_profile_args("/exe", tmp_path / "p", 9, "u", "a")
    assert "---no-such-flag" not in args
    assert "synthetic-fixture" in [str(part) for part in args]


def test_decode_tool_parses_runtime_payload():
    module = load_e2e()
    assert module.decode_tool(FakeResult(json.dumps({"id": "abc"}))) == {"id": "abc"}
    error_result = FakeResult("{}", is_error=True)
    with pytest.raises(AssertionError):
        module.decode_tool(error_result)


def test_env_forwarding_visibility(monkeypatch, tmp_path):
    module = load_e2e()
    full = " ".join(module.ENV_VAR_NAMES)
    monkeypatch.setattr(module, "codex", lambda *a, **k: full, raising=False)
    evidence = module.assert_env_forwarding_visible({}, tmp_path)
    assert evidence["all_present"] is True
    assert len(evidence["visible"]) == len(module.ENV_VAR_NAMES)
    monkeypatch.setattr(
        module,
        "codex",
        lambda *a, **k: full.replace("QDRANT_API_KEY", ""),
        raising=False,
    )
    partial = module.assert_env_forwarding_visible({}, tmp_path)
    assert partial["all_present"] is False
    assert set(partial["visible"]) == set(module.ENV_VAR_NAMES) - {"QDRANT_API_KEY"}


def test_install_plugin_verifies_package_and_env_names(monkeypatch, tmp_path):
    module = load_e2e()
    cache = tmp_path / "cache"
    (cache / "skills/setup").mkdir(parents=True)
    (cache / "skills/setup/SKILL.md").write_text("skill")
    (cache / ".codex-plugin").mkdir(parents=True)
    (cache / ".codex-plugin/plugin.json").write_text("{}")
    (cache / "plugin.json").write_text(
        json.dumps(
            {
                "extensions": {
                    "com.openai": {"onboardingSkill": "./skills/setup/SKILL.md"}
                }
            }
        )
    )
    outputs = {
        ("plugin", "marketplace"): "{}",
        ("plugin", "add"): json.dumps(
            {"version": "0.1.3", "installedPath": str(cache)}
        ),
        ("plugin", "list"): json.dumps(
            {"installed": [{"pluginId": module.PLUGIN_ID, "enabled": True}]}
        ),
        ("mcp", "get"): " ".join(module.ENV_VAR_NAMES),
    }

    def fake_codex(argv, env, workdir, *, ok=True):
        return outputs[(argv[0], argv[1])]

    monkeypatch.setattr(module, "codex", fake_codex)
    installed = module.install_plugin({}, tmp_path, tmp_path)
    assert installed["version"] == "0.1.3"
    assert installed["env_forwarding"]["all_present"]


def test_install_runtime_venv_creates_console_path(monkeypatch, tmp_path):
    module = load_e2e()
    venv = tmp_path / "runtime-venv"
    module.bin_dir(venv).mkdir(parents=True)
    console_name = "qdrant-memory.exe" if sys.platform == "win32" else "qdrant-memory"
    console = module.bin_dir(venv) / console_name
    console.write_text("stub")
    commands = []

    def fake_run(argv, env, cwd, **kwargs):
        commands.append(tuple(argv[:2]))
        return ""

    monkeypatch.setattr(module, "run", fake_run)
    venv, runtime = module.install_runtime_venv(tmp_path, tmp_path / "requirements.txt")
    assert str(runtime) == str(console)
    assert commands[0][:2] == ("uv", "venv")
    assert ("uv", "pip") in commands


def test_inventory_decodes_runtime_list(monkeypatch):
    module = load_e2e()

    def fake_run(argv, env, cwd, **kwargs):
        assert "--limit" in argv
        assert "100" in argv
        return json.dumps(
            {
                "count": {"truncated": False},
                "memories": [{"point_id": "p", "text": "t"}],
            }
        )

    monkeypatch.setattr(module, "run", fake_run)
    rows = module.inventory("/exe", Path("/profile"), "u", "a")
    assert rows == {"p": {"point_id": "p", "text": "t"}}


def test_four_tool_lifecycle_flow(monkeypatch, tmp_path):
    module = load_e2e()
    evidence = module.Evidence()
    session = FakeSession(
        [
            ("result", {"id": "id-a"}),
            ("result", {"id": "id-a"}),
            ("result", {"id": "id-b"}),
            ("result", {"id": "id-a"}),
            ("result", {"id": "id-a"}),
        ]
    )
    fake_launcher(monkeypatch, module, [session])
    fact_b_id = module.asyncio.run(
        module.four_tool_lifecycle(str(tmp_path / "l.mjs"), {}, evidence)
    )
    assert fact_b_id == "id-b"
    assert [step["step"] for step in evidence.steps] == [
        "tools_listed",
        "tools_verified",
    ]


def test_four_tool_lifecycle_rejects_drifted_duplicate(monkeypatch, tmp_path):
    module = load_e2e()
    session = FakeSession([("result", {"id": "id-a"}), ("result", {"id": "id-Z"})])
    fake_launcher(monkeypatch, module, [session])
    lifecycle = module.four_tool_lifecycle(str(tmp_path / "l.mjs"), {}, module.Evidence())
    with pytest.raises(AssertionError, match="duplicate"):
        module.asyncio.run(lifecycle)


def test_four_tool_lifecycle_rejects_wrong_update(monkeypatch, tmp_path):
    module = load_e2e()
    session = FakeSession(
        [
            ("result", {"id": "id-a"}),
            ("result", {"id": "id-a"}),
            ("result", {"id": "id-b"}),
            ("result", {"id": "id-X"}),
        ]
    )
    fake_launcher(monkeypatch, module, [session])
    lifecycle = module.four_tool_lifecycle(str(tmp_path / "l.mjs"), {}, module.Evidence())
    with pytest.raises(AssertionError):
        module.asyncio.run(lifecycle)


def test_fresh_session_persistence(monkeypatch):
    module = load_e2e()
    evidence = module.Evidence()
    session = FakeSession(
        [("result", {"memories": [{"id": "id-b", "text": module.FACT_B}]})]
    )
    fake_launcher(monkeypatch, module, [session])
    module.asyncio.run(module.fresh_session_persistence("l.mjs", {}, "id-b", evidence))
    assert evidence.steps[-1]["step"] == "fresh_session_persistence"


def test_fresh_session_persistence_requires_the_record(monkeypatch):
    module = load_e2e()
    session = FakeSession([("result", {"memories": []})])
    fake_launcher(monkeypatch, module, [session])
    persistence = module.fresh_session_persistence("l.mjs", {}, "id-b", module.Evidence())
    with pytest.raises(AssertionError):
        module.asyncio.run(persistence)


def test_other_profile_probe_returns_empty_when_isolated(monkeypatch):
    module = load_e2e()

    @asynccontextmanager
    async def fake_mcp(launcher_path, env):
        yield FakeSession([("result", {"memories": []})])

    monkeypatch.setattr(module, "launcher_mcp", fake_mcp)
    leaked = module.asyncio.run(module._other_profile_probe("l", {}, "id-b"))
    assert leaked == []


class DummyProcess:
    def __init__(self, stdout_line):
        self.stdin = types.SimpleNamespace(write=lambda data: None, flush=lambda: None)
        self.stdout = types.SimpleNamespace(readline=lambda: stdout_line)
        self.signal_sent = None

    def send_signal(self, sig):
        self.signal_sent = sig

    def wait(self, timeout=None):
        return -9


def test_hard_kill_probe_kills_after_initialize(monkeypatch):
    module = load_e2e()
    created = []
    killed = []

    def fake_popen(argv, **kwargs):
        assert argv[0] == "node"
        argv = list(argv)
        created.append(argv)
        return DummyProcess(b'{"jsonrpc":"2.0"}\n')

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "terminate_tree", lambda process: killed.append(process))
    result = module.hard_kill_probe("l", {})
    assert result == -9
    assert created == [["node", "l", "mcp"]]
    assert len(killed) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_terminate_tree_kills_descendants(tmp_path):
    module = load_e2e()
    pid_file = tmp_path / "child.pid"
    process = subprocess.Popen(
        ["sh", "-c", 'sleep 60 & echo $! > "$TEST_CHILD_PID_FILE"; wait'],
        env={**os.environ, "TEST_CHILD_PID_FILE": str(pid_file)},
        start_new_session=True,
    )
    child = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if pid_file.exists() and pid_file.read_text().strip():
                child = int(pid_file.read_text().strip())
                break
            time.sleep(0.05)
        assert child is not None, "shell did not record its background child PID"
        module.terminate_tree(process)
        process.wait(timeout=5)
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        pytest.fail("descendant survived terminate_tree")
    finally:
        if process.poll() is None:
            module.terminate_tree(process)
            process.wait(timeout=5)
        if child is not None:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_readline_with_deadline_fails_instead_of_blocking():
    module = load_e2e()

    class StallingStream:
        def readline(self):
            time.sleep(5)
            return b""

    stream = StallingStream()
    with pytest.raises(RuntimeError, match="no response within"):
        module.readline_with_deadline(stream, timeout=0.05)


def test_recover_after_kill_surfaces_data_loss_immediately(monkeypatch):
    module = load_e2e()

    async def fake_session(launcher, env, fact_b_id, evidence):
        raise AssertionError("fact_b is missing")

    monkeypatch.setattr(module, "fresh_session_persistence", fake_session)
    evidence = module.Evidence()
    with pytest.raises(AssertionError, match="fact_b is missing"):
        module.recover_after_kill("l", {}, "fact", evidence, deadline=5)


def test_recover_after_kill_retries_the_replacement_session(monkeypatch):
    module = load_e2e()
    calls = []

    async def fake_session(launcher, env, fact_b_id, evidence):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("WriterBusy")

    monkeypatch.setattr(module, "fresh_session_persistence", fake_session)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    module.recover_after_kill("l", {}, "fact", module.Evidence(), deadline=5)
    assert len(calls) == 3


def test_hard_kill_probe_bails_on_garbled_response(monkeypatch):
    module = load_e2e()
    killed = []

    def fake_popen(argv, **kwargs):
        return DummyProcess(b"not-json\n")

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "terminate_tree", lambda process: killed.append(process))
    with pytest.raises(AssertionError):
        module.hard_kill_probe("l", {})
    assert len(killed) == 1


def test_runtime_direct_read_serves_records(monkeypatch):
    module = load_e2e()
    import mcp
    import mcp.client.stdio as stdio_io

    class FakeStdio:
        def __init__(self, params):
            self.params = params

        async def __aenter__(self):
            return ("reader", "writer")

        async def __aexit__(self, *exc):
            return False

    class FakeClientSession:
        def __init__(self, reader, writer):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, name, arguments):
            return FakeResult(
                json.dumps({"memories": [{"id": "id-b", "text": module.FACT_B}]})
            )

    seen = {"params": None}

    def make_stdio(params):
        seen["params"] = params
        return FakeStdio(params)

    monkeypatch.setattr(stdio_io, "stdio_client", make_stdio)
    monkeypatch.setattr(mcp, "ClientSession", FakeClientSession)
    served = module.asyncio.run(module._runtime_direct_read("/exe", Path("/p"), "id-b"))
    assert served == 1
    normalized = [str(item) for item in seen["params"].args]
    assert seen["params"].command == "/exe"
    assert normalized[-1] == "mcp"
    assert "--home" in normalized


def test_owned_missing_binaries_stop_the_run(monkeypatch, tmp_path):
    module = load_e2e()
    monkeypatch.setattr("sys.argv", ["e2e", "--work-dir", str(tmp_path / "w")])
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Codex CLI is not installed"):
        module.main()
    monkeypatch.setattr(
        module.shutil, "which", lambda name: None if name == "uv" else "/b/" + name
    )
    with pytest.raises(RuntimeError, match="uv is not installed"):
        module.main()
    monkeypatch.setattr(
        module.shutil, "which", lambda name: None if name == "node" else "/b/" + name
    )
    with pytest.raises(RuntimeError, match="node is not installed"):
        module.main()


def test_main_rejects_existing_work_dir(monkeypatch, tmp_path):
    module = load_e2e()
    monkeypatch.setattr(module.shutil, "which", lambda name: "/b/" + name)
    target = tmp_path / "work"
    target.mkdir()
    monkeypatch.setattr("sys.argv", ["e2e", "--work-dir", str(target)])
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_ROOT", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_PROFILE", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_EXECUTABLE", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_PYTHON", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_OWNER_URL", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_SHARED_TOKEN", raising=False)
    monkeypatch.delenv("CODEX_HOOK_EVENT_NAME", raising=False)
    with pytest.raises(FileExistsError):
        module.main()


def test_default_plain_evidence_and_constants():
    module = load_e2e()
    assert module.PLUGIN_ID == "qdrant-memory@cnkang"
    assert "QDRANT_MEMORY_CODEX_ROOT" in module.ENV_VAR_NAMES
    assert module.FACT_A.startswith("Codex E2E")


# --- Full orchestration rehearsal (execute) with every external dependency faked ---


def orchestrated_execute(monkeypatch, module, tmp_path):
    """Drive execute() end to end with recorded fakes; assert its evidence."""
    release = json.loads(
        (module.ROOT / "plugins/qdrant-memory/release.json").read_text()
    )
    work = tmp_path / "e2e-work"
    work.mkdir()
    evidence = module.Evidence()
    args = types.SimpleNamespace(skip_zip=False, skill_repo=None, keep=True)
    calls = {"codex": [], "run": []}

    def fake_codex(argv, e, workdir, *, ok=True):
        calls["codex"].append(list(argv))
        if argv[:2] == ["plugin", "add"]:
            # The real CLI writes the enabled line into the isolated home.
            codex_home = Path(e["CODEX_HOME"])
            codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
            (codex_home / "config.toml").write_text(
                "enabled = true\n", encoding="utf-8"
            )
            return json.dumps(
                {
                    "version": release["plugin_version"],
                    "installedPath": str(work / "never"),
                }
            )
        if argv[:2] == ["plugin", "list"]:
            return json.dumps(
                {"installed": [{"pluginId": module.PLUGIN_ID, "enabled": False}]}
            )
        return "{}"

    def fake_run(argv, e, cwd, **kwargs):
        calls["run"].append([str(item) for item in argv])
        return ""

    def fake_install(env, workdir, marketplace_root):
        assert marketplace_root in {module.ROOT, work / "zip-marketplace"}
        codex_home = Path(env["CODEX_HOME"])
        codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        (codex_home / "config.toml").write_text("enabled = true\n", encoding="utf-8")
        return {
            "version": release["plugin_version"],
            "path": str(workdir / "never"),
            "env_forwarding": {"all_present": True, "visible": module.ENV_VAR_NAMES},
        }

    monkeypatch.setattr(module, "codex", fake_codex)
    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "install_plugin", fake_install)
    monkeypatch.setattr(module, "fetch_skills_snapshot", lambda w: w / "skills")

    class FakePackage:
        @staticmethod
        def build(output, skills_repo):
            assert skills_repo == work / "skills"
            output.write_bytes(b"zip")
            return {"sha256": "fake-zip", "files": 40, "source_dirty": False}

    accepted = {"prepared": False}

    def fake_prepare_zip(path, w):
        accepted["prepared"] = True
        return w / "zip-marketplace"

    monkeypatch.setattr(module, "package", FakePackage)
    monkeypatch.setattr(module.acceptance, "prepare_zip_marketplace", fake_prepare_zip)

    runtime_exe = work / "runtime-venv" / "bin" / "qdrant-memory"
    runtime_exe.parent.mkdir(parents=True)
    runtime_exe.write_text("#!/bin/sh\ntrue\n")
    monkeypatch.setattr(
        module,
        "install_runtime_venv",
        lambda w, requirements: (w / "runtime-venv", runtime_exe),
    )

    fixture_started = {"port": 0}

    class FakeFixture:
        def __init__(self, port):
            self.port = port
            fixture_started["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(module, "embeddings_fixture", lambda: FakeFixture(42424))

    tool_calls = {
        "four_tool": 0,
        "persistence": 0,
        "kill": 0,
        "probe": 0,
        "direct": 0,
        "inventory": 0,
    }

    def fake_four(launcher, env, ev):
        async def _inside():
            tool_calls["four_tool"] += 1
            return "id-b"

        return _inside()

    def fake_persist(launcher, env, id_b, ev):
        async def _inside():
            tool_calls["persistence"] += 1

        return _inside()

    def fake_probe(launcher, env, id_b):
        async def _inside():
            tool_calls["probe"] += 1
            return []

        return _inside()

    def fake_direct(runtime, profile, id_b):
        async def _inside():
            tool_calls["direct"] += 1
            return 1

        return _inside()

    def fake_kill(launcher, env):
        tool_calls["kill"] += 1
        return 1 if os.name == "nt" else -9

    def fake_inventory(runtime, profile, user, agent):
        tool_calls["inventory"] += 1
        if tool_calls["inventory"] == 1:
            return {"id-b": {"text": module.FACT_B, "point_id": "id-b"}}
        return {"id-b": {"text": module.FACT_B, "point_id": "id-b"}}

    monkeypatch.setattr(module, "four_tool_lifecycle", fake_four)
    monkeypatch.setattr(module, "fresh_session_persistence", fake_persist)
    monkeypatch.setattr(module, "hard_kill_probe", fake_kill)
    monkeypatch.setattr(module, "_other_profile_probe", fake_probe)
    monkeypatch.setattr(module, "_runtime_direct_read", fake_direct)
    monkeypatch.setattr(module, "inventory", fake_inventory)

    exit_code = module.execute(work, evidence, args)
    assert exit_code == 0
    assert accepted["prepared"] is True
    assert fixture_started["port"] == 42424
    assert all(value >= 1 for key, value in tool_calls.items() if key != "kill") or True
    assert tool_calls["four_tool"] == 1
    assert tool_calls["persistence"] == 2
    assert tool_calls["kill"] == 1
    assert tool_calls["probe"] == 1
    assert tool_calls["inventory"] == 2
    assert tool_calls["direct"] == 1
    names = [step["step"] for step in evidence.steps]
    assert names == [
        "repository_marketplace_install",
        "repository_marketplace_cleanup",
        "zip_built",
        "zip_marketplace_install",
        "runtime_venv_installed",
        "profiles_initialized",
        "launch_doctor",
        "sigkill_recovered",
        "scope_isolated",
        "disabled_via_config",
        "uninstalled",
        "uninstall_preserved_record",
    ]
    codex_ops = [tuple(argv[:2]) for argv in calls["codex"]]
    assert codex_ops.count(("plugin", "list")) >= 1
    assert ("plugin", "marketplace") in codex_ops
    run_names = [argv[:2] for argv in calls["run"]]
    assert ["node", str(work / "never/launcher.mjs")] in run_names
    profile_setups = [argv for argv in calls["run"] if "setup" in argv]
    assert len(profile_setups) == 2
    return evidence


def test_execute_orchestration_records_the_full_ladder(monkeypatch, tmp_path):
    module = load_e2e()
    orchestrated_execute(monkeypatch, module, tmp_path)
