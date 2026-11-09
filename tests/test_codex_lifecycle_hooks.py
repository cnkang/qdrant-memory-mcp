"""Optional lifecycle-mode hook handlers: released contract and safe behavior."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "integrations/codex-lifecycle/plugin/hooks"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_bytecode_cache(monkeypatch):
    """Keep hook sources pristine: loader must not write __pycache__."""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)


@pytest.fixture
def hook_env(tmp_path, monkeypatch):
    """Point the hooks at a private root with a stub Runtime console script."""
    runtime_root = tmp_path / "codex-root"
    profile = runtime_root / "profile"
    profile.mkdir(parents=True)
    (profile / "qdrant-memory.json").write_text(
        json.dumps(
            {
                "scope": {"user_id": "hook-user", "agent_id": "hook-agent"},
                "embedding": {"dimensions": 1},
            }
        ),
        encoding="utf-8",
    )
    scratch = tmp_path / "stub-bin"
    scratch.mkdir()
    stub = scratch / "qdrant-memory"
    stub.write_text("#!/bin/sh\nexec true\n")
    stub.chmod(0o755)
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_ROOT", str(runtime_root))
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_EXECUTABLE", str(stub))
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_PROFILE", str(profile))
    return {"profile": profile, "stub": stub, "runtime_root": runtime_root}


def test_digest_configuration_pins_official_events():
    """hooks.json must keep the documented events and safe thresholds."""
    hooks = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    assert set(hooks["hooks"]) == {"SessionStart", "UserPromptSubmit"}
    start = hooks["hooks"]["SessionStart"][0]
    assert start["matcher"] == "startup|resume|clear|compact|fork"
    assert start["hooks"][0]["type"] == "command"
    assert "${PLUGIN_ROOT}/hooks/session_recall.py" in start["hooks"][0]["command"]
    assert start["hooks"][0]["additionalContextLimit"] > 0
    capture = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert "${PLUGIN_ROOT}/hooks/user_prompt_capture.py" in capture["command"]
    assert "Stop" not in hooks["hooks"]  # no fabricated auto-capture


def test_main_plugin_package_contains_no_hooks():
    """The public-ready plugin keeps its submission eligibility (no hooks)."""
    manifest = json.loads(
        (ROOT / "plugins/qdrant-memory/plugin.json").read_text(encoding="utf-8")
    )
    assert "hooks" not in manifest["extensions"]["com.openai"]
    overlay = json.loads(
        (ROOT / "plugins/qdrant-memory/.codex-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert "hooks" not in json.dumps(overlay)
    assert not (ROOT / "plugins/qdrant-memory/hooks").exists()


def test_explicit_capture_saves_directive_text(hook_env, monkeypatch, capsys):
    """The real handler saves exactly the remainder of a remember: line."""
    load("user_prompt_capture")  # syntax check against the real file
    module = load("user_prompt_capture")
    saved = []

    def fake_call(*args, **kwargs):
        saved.append(list(args))
        return 0, json.dumps({"id": "stub-id"}), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin", type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "Remember: dish soap runs low."}))})()
    )
    module.main()
    output = capsys.readouterr().out.strip()
    assert "hookSpecificOutput" not in output  # no model-visible injection
    assert "systemMessage" in json.loads(output)
    assert saved == [["add", "--text", "dish soap runs low."]]


def test_explicit_capture_ignores_non_directives(hook_env, monkeypatch, capsys):
    module = load("user_prompt_capture")
    saved = []

    def fake_call(*args, **kwargs):
        saved.append(list(args))
        return 0, "{}", ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(
        "sys.stdin", type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "tell me a joke"}))})()
    )
    module.main()
    assert saved == []
    assert capsys.readouterr().out == ""


def test_explicit_capture_rejects_oversized_lines(hook_env, monkeypatch, capsys):
    module = load("user_prompt_capture")
    saved = []

    def fake_call(*args, **kwargs):
        saved.append(list(args))
        return 0, "{}", ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "remember: " + "x" * 600}))})(),
    )
    module.main()
    assert saved == []
    assert "did not save" in capsys.readouterr().out


def test_session_recall_emits_additional_context(hook_env, monkeypatch, capsys):
    module = load("session_recall")
    queries = []

    def fake_call(*args, **kwargs):
        queries.append(args)
        rows = {"memories": [{"text": "Prefers green notebooks."}]}
        return 0, json.dumps(rows), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"cwd": "/tmp/demo-project", "source": "resume"}))})(),
    )
    module.main()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "Prefers green notebooks." in context
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert queries == [("search", "--query", "demo-project")]


def test_session_recall_stays_silent_without_matches(hook_env, monkeypatch, capsys):
    module = load("session_recall")

    def fake_call(*args, **kwargs):
        return 0, json.dumps({"memories": []}), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"cwd": "/tmp/empty"}))})(),
    )
    module.main()
    assert capsys.readouterr().out == ""


def test_session_recall_reports_runtime_failure_gradefully(hook_env, monkeypatch, capsys):
    module = load("session_recall")

    def fake_call(*args, **kwargs):
        return 3, "", "Runtime missing"

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin", type("S", (), {"read": staticmethod(lambda: json.dumps({"cwd": "/x"}))})()
    )
    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert "Runtime missing" in payload["systemMessage"]
    assert "hookSpecificOutput" not in payload


def test_safe_error_prefers_stderr_then_stdout(hook_env):
    runtime = load("session_recall").runtime
    assert runtime.safe_error("stdout", "stderr\nignored") == "stderr"
    assert runtime.safe_error("stdout\nignored", "  ") == "stdout"
    assert runtime.safe_error(" ", "") == "unknown error"


def test_emit_without_payload_stays_silent(hook_env, capsys):
    runtime = load("session_recall").runtime
    runtime.emit()
    assert capsys.readouterr().out == ""


def test_session_recall_requires_session_cwd(monkeypatch, capsys):
    module = load("session_recall")
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_ROOT", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_PROFILE", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_EXECUTABLE", raising=False)
    calls = []

    def fake_call(*args, **kwargs):
        calls.append(args)
        return 0, json.dumps({"memories": [{"text": "x"}]}), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    monkeypatch.setattr(
        "sys.stdin", type("S", (), {"read": staticmethod(lambda: "")})()
    )
    module.main()
    output = capsys.readouterr().out.strip()
    payload = json.loads(output) if output else {}
    assert "systemMessage" in payload  # no cwd → skip, with a message


def test_runtime_paths_follow_overrides(hook_env):
    """The executable contract follows the launcher environment overrides."""
    runtime = load("lifecycle_runtime")
    assert runtime.profile_path() == hook_env["profile"]
    assert runtime.runtime_executable() == hook_env["stub"]
    assert runtime.load_scope() == ("hook-user", "hook-agent")


def test_runtime_paths_follow_default_layout(monkeypatch, home_override):
    """Without overrides the hook resolves the documented default layout."""
    runtime = load("lifecycle_runtime")
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_ROOT", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_PROFILE", raising=False)
    monkeypatch.delenv("QDRANT_MEMORY_CODEX_EXECUTABLE", raising=False)
    platform = ("Scripts", "qdrant-memory.exe") if sys.platform == "win32" else ("bin", "qdrant-memory")
    assert runtime.profile_path() == home_override / ".qdrant-memory" / "codex" / "profile"
    assert runtime.runtime_executable() == home_override / ".qdrant-memory" / "codex" / "runtime" / platform[0] / platform[1]


@pytest.fixture
def home_override(monkeypatch):
    """Redirect home for default-layout checks."""
    import tempfile

    base = Path(tempfile.mkdtemp())
    monkeypatch.setenv("HOME", str(base))
    monkeypatch.setenv("USERPROFILE", str(base))
    if sys.platform == "win32":
        monkeypatch.setenv("HOMEDRIVE", "")
        monkeypatch.setenv("HOMEPATH", str(base))
    yield base
    shutil.rmtree(base, ignore_errors=True)


def test_lifecycle_scope_enforcement_failures(hook_env, monkeypatch):
    """Broken scope fails closed; no fallback scope is invented."""
    runtime = load("lifecycle_runtime")
    broken = hook_env["profile"] / "qdrant-memory.json"
    broken.write_text(json.dumps({"scope": {}}), encoding="utf-8")
    with pytest.raises(runtime.HookError, match="incomplete"):
        runtime.load_scope()
    broken.unlink()
    with pytest.raises(runtime.HookError):
        runtime.load_scope()
