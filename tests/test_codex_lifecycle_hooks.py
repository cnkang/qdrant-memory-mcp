"""Optional lifecycle-mode hook handlers: released contract and safe behavior."""

import importlib.util
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "integrations/codex-lifecycle/plugin/hooks"


def load(name):
    """Load (or reuse the imported) hook module, so patches hit the shared object."""
    registered = sys.modules.get(name)
    if registered is not None and getattr(registered, "__file__", None) == str(
        HOOKS / f"{name}.py"
    ):
        return registered
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # hook files import each other through this cache
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
    assert set(hooks["hooks"]) == {
        "SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"
    }
    start = hooks["hooks"]["SessionStart"][0]
    assert start["matcher"] == "startup|resume|clear|compact|fork"
    assert start["hooks"][0]["type"] == "command"
    assert "${PLUGIN_ROOT}/hooks/session_recall.py" in start["hooks"][0]["command"]
    assert start["hooks"][0]["additionalContextLimit"] > 0
    capture = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert "${PLUGIN_ROOT}/hooks/user_prompt_capture.py" in capture["command"]
    stop = hooks["hooks"]["Stop"][0]["hooks"][0]
    assert "${PLUGIN_ROOT}/hooks/turn_capture.py" in stop["command"]
    assert stop["async"] is True  # capture must never add turn latency
    stop_timeout = hooks["hooks"]["Stop"][0]["hooks"][0]
    assert stop_timeout["timeout"] <= 30
    session_end = hooks["hooks"]["SessionEnd"][0]["hooks"][0]
    assert "${PLUGIN_ROOT}/hooks/prune_scratch.py" in session_end["command"]
    assert session_end["timeout"] <= 3  # SessionEnd default/max window


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
        "sys.stdin", type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "Remember:  dish soap runs low."}))})()
    )
    module.main()
    output = capsys.readouterr().out.strip()
    assert "hookSpecificOutput" not in output  # no model-visible injection
    assert "systemMessage" in json.loads(output)
    assert saved == [["add", "--text", "  dish soap runs low."]]


def test_explicit_capture_preserves_trailing_whitespace(hook_env, monkeypatch, capsys):
    module = load("user_prompt_capture")
    saved = []

    def fake_call(*args, **kwargs):
        saved.append(list(args))
        return 0, json.dumps({"id": "stub-id"}), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "remember: keep two spaces  "}))})(),
    )
    module.main()
    assert saved == [["add", "--text", " keep two spaces  "]]


def test_explicit_capture_accepts_a_full_width_colon(hook_env, monkeypatch, capsys):
    module = load("user_prompt_capture")
    saved = []

    def fake_call(*args, **kwargs):
        saved.append(list(args))
        return 0, json.dumps({"id": "stub-id"}), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "remember：中文事实"}))})(),
    )
    module.main()
    assert saved == [["add", "--text", "中文事实"]]


def test_explicit_capture_ignores_a_blank_directive(hook_env, monkeypatch, capsys):
    module = load("user_prompt_capture")
    saved = []

    def fake_call(*args, **kwargs):
        saved.append(list(args))
        return 0, "{}", ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"prompt": "remember:   "}))})(),
    )
    module.main()
    assert saved == []
    assert capsys.readouterr().out == ""


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


def test_session_recall_stays_silent_when_rows_have_no_text(hook_env, monkeypatch, capsys):
    module = load("session_recall")

    def fake_call(*args, **kwargs):
        return 0, json.dumps({"memories": [{"id": "one"}, {"text": "   "}]}), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake_call)
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("hook-user", "hook-agent"))
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"read": staticmethod(lambda: json.dumps({"cwd": "/tmp/blank"}))})(),
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


# --- Auto-capture: pairing and Stop-time journaling (Phase 1) ---


def feed_stdin(monkeypatch, payload_bytes_or_dict):
    """Replace stdin with one JSON hook event."""
    raw = payload_bytes_or_dict if isinstance(payload_bytes_or_dict, str) else json.dumps(payload_bytes_or_dict)
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: raw)})())


def stage_scratch(monkeypatch, runtime, *, prompt="plain question", session="sess-1", turn="t-1", cwd="/work"):
    """Stage the pairing scratch exactly as the UserPromptSubmit hook does."""
    capture = load("user_prompt_capture")
    feed_stdin(monkeypatch, {
        "session_id": session, "turn_id": turn, "cwd": cwd, "prompt": prompt
    })
    assert capture.main() is None


def test_user_prompt_submit_stages_scratch_and_honors_remember(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    # The remember branch must be testable on every OS; monkeypatching avoids
    # executing a POSIX-only stub console script on Windows.
    call = []

    def fake_call(*args, **kwargs):
        call.append(list(args))
        return 0, json.dumps({"id": "rec-1"}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_call)
    stage_scratch(monkeypatch, runtime, prompt="Remember: team offsite is in May.")
    output = json.loads(capsys.readouterr().out.strip())
    assert "saved one explicit fact" in output["systemMessage"]
    assert call == [["add", "--text", "team offsite is in May."]]
    scratch = runtime.scratch_path_for("sess-1", "t-1")
    staged = json.loads(scratch.read_text(encoding="utf-8"))
    assert staged["session_id"] == "sess-1"
    assert staged["turn_id"] == "t-1"
    assert staged["user_excerpt"] == "Remember: team offsite is in May."


def test_user_prompt_submit_scratch_records_excerpt(hook_env, monkeypatch):
    stage_scratch(monkeypatch, load("lifecycle_runtime"))
    runtime = load("lifecycle_runtime")
    staged = json.loads(
        runtime.scratch_path_for("sess-1", "t-1").read_text(encoding="utf-8")
    )
    assert staged["user_excerpt"] == "plain question"
    assert staged["user_truncated"] is False
    assert staged["cwd"] == "/work"


def test_scratch_prefers_plugin_data_and_cleans(hook_env, monkeypatch, tmp_path):
    plugin_data = tmp_path / "plugin-data"
    monkeypatch.setenv("PLUGIN_DATA", str(plugin_data))
    runtime = load("lifecycle_runtime")
    stage_scratch(monkeypatch, runtime)
    staged = plugin_data / "turn_inputs"
    assert staged.is_dir()
    assert list(staged.glob("*.json"))
    assert not (runtime.events_root() / "scratch").exists()


def test_stop_capture_pairs_and_writes_bounded_pending_event(hook_env, monkeypatch, capsys):
    stage_scratch(monkeypatch, load("lifecycle_runtime"))
    stop = load("turn_capture")
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1",
        "last_assistant_message": "Storage caps are 300 pending events per profile.",
        "stop_hook_active": False,
    })
    assert stop.main() is None
    runtime = load("lifecycle_runtime")
    events = sorted(runtime.pending_dir().glob("*.json"))
    assert len(events) == 1
    stored = json.loads(events[0].read_text(encoding="utf-8"))
    assert stored["status"] == "pending"
    assert stored["user_text"]["excerpt"] == "plain question"
    assert "300 pending events" in stored["assistant_text"]["text"]
    assert events[0].name == runtime.event_id_for("sess-1", "t-1") + ".json"
    assert stored["provenance"]["capture_source"] == "codex-hook"
    # The pairing scratch is consumed by the Stop hook.
    assert not runtime.scratch_path_for("sess-1", "t-1").exists()
    assert capsys.readouterr().out == ""


def test_stop_capture_is_idempotent_per_turn(hook_env, monkeypatch):
    runtime = load("lifecycle_runtime")
    stop = load("turn_capture")
    for _ in range(2):
        stage_scratch(monkeypatch, runtime)
        feed_stdin(monkeypatch, {
            "session_id": "sess-1", "turn_id": "t-1",
            "last_assistant_message": "reply text",
        })
        assert stop.main() is None
    assert len(list(runtime.pending_dir().glob("*.json"))) == 1
    assert not runtime.scratch_path_for("sess-1", "t-1").exists()


def test_stop_capture_byte_bounds_assistant_text(hook_env, monkeypatch):
    stage_scratch(monkeypatch, load("lifecycle_runtime"))
    stop = load("turn_capture")
    runtime = load("lifecycle_runtime")
    long_reply = "x" * (runtime.ASSISTANT_TEXT_BYTES + 64)
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1", "last_assistant_message": long_reply
    })
    assert stop.main() is None
    stored = json.loads(next(runtime.pending_dir().glob("*.json")).read_text(encoding="utf-8"))
    assert len(stored["assistant_text"]["text"].encode("utf-8")) <= runtime.ASSISTANT_TEXT_BYTES
    assert stored["assistant_text"]["truncated"] is True


def test_stop_capture_without_pairing_captures_nothing(hook_env, monkeypatch):
    stop = load("turn_capture")
    runtime = load("lifecycle_runtime")
    feed_stdin(monkeypatch, {
        "session_id": "sess-2", "turn_id": "t-9",
        "last_assistant_message": "orphan assistant text",
    })
    assert stop.main() is None
    assert list(runtime.pending_dir().glob("*.json")) == []


def test_stop_capture_requires_assistant_text(hook_env, monkeypatch):
    stage_scratch(monkeypatch, load("lifecycle_runtime"))
    stop = load("turn_capture")
    runtime = load("lifecycle_runtime")
    feed_stdin(monkeypatch, {"session_id": "sess-1", "turn_id": "t-1"})
    assert stop.main() is None
    assert list(runtime.pending_dir().glob("*.json")) == []
    # A blank pairing entry never surfaces either.
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1", "last_assistant_message": "  "
    })
    assert stop.main() is None
    assert list(runtime.pending_dir().glob("*.json")) == []


def test_stop_capture_never_invokes_the_runtime(hook_env, monkeypatch):
    """The capture path is storage-local: the Runtime binary must stay closed."""
    stage_scratch(monkeypatch, load("lifecycle_runtime"))
    stop = load("turn_capture")
    invocations = []

    def spy(*args, **kwargs):
        invocations.append(args)
        return 0, "", ""

    monkeypatch.setattr(load("lifecycle_runtime"), "call_runtime", spy)
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1",
        "last_assistant_message": "reply",
    })
    assert stop.main() is None
    assert invocations == []


def test_stop_capture_overflow_prepares_and_pauses(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    stop = load("turn_capture")
    monkeypatch.setattr(runtime, "pending_count", lambda: runtime.MAX_PENDING_EVENTS)
    stage_scratch(monkeypatch, runtime)
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1",
        "last_assistant_message": "reply",
    })
    assert stop.main() is None
    assert list(runtime.pending_dir().glob("*.json")) == []  # nothing appended
    assert runtime.count_overflow_marker() == 1
    body = json.loads(capsys.readouterr().out.strip())
    assert "pending buffer is full" in body["systemMessage"]
    assert "reply" not in body["systemMessage"]


def test_prune_stale_scratch_respects_ttl(hook_env, monkeypatch):
    runtime = load("lifecycle_runtime")
    stage_scratch(monkeypatch, runtime)
    scratch = runtime.scratch_path_for("sess-1", "t-1")
    assert scratch.exists()
    old = 0 if runtime.SCRATCH_TTL_SECONDS > 0 else 1
    _ = old  # ttl semantics exercised below via timestamp math
    ttl = runtime.SCRATCH_TTL_SECONDS

    fresh_poll = runtime.prune_stale_scratch(now=scratch.stat().st_mtime + ttl + 1)
    assert fresh_poll == 1
    assert not scratch.exists()


# --- Extractor (Phase 2): dry-run contract, validation, confirm admission ---


def extraction_provider_stub(monkeypatch, replies):
    """Serve the OpenAI-compatible extraction endpoint from a local server."""
    import threading

    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            reply = replies.pop(0) if replies else {"choices": [{"message": {"content": "{\"memories\": []}"}}]}
            payload = (json.dumps(reply).encode("utf-8"), 200)
            self.send_response(payload[1])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload[0])))
            self.end_headers()
            self.wfile.write(payload[0])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, calls
    server.shutdown()
    server.server_close()


def stage_pending(hook_env, monkeypatch, runtime, *, user="user turn", assistant="assistant turn",
                  session="sess-1", turn="t-1"):
    stage_scratch(monkeypatch, runtime, prompt=user, session=session, turn=turn)
    stop = load("turn_capture")
    feed_stdin(monkeypatch, {
        "session_id": session, "turn_id": turn, "last_assistant_message": assistant
    })
    assert stop.main() is None


def extractor_args(monkeypatch, server_port, model="fixture-extractor"):
    argv = [
        "--base-url", f"http://127.0.0.1:{server_port}/v1",
        "--model", model,
        "--limit", "5",
    ]
    return argv


def extractor_cli():
    return load("extract_pending")


def test_extractor_dry_run_lists_candidates_without_writes(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="I prefer round mugs", assistant="Noted the preference.")
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{"text": "Prefers round mugs.", "category": ["codex-auto"], "importance": 0.7}]
        })}}]
    }]
    calls = []
    for server, provider_calls in extraction_provider_stub(monkeypatch, replies):
        calls = provider_calls
        argv = extractor_args(monkeypatch, server.server_port)
        exit_code = cli.main(argv)
        assert exit_code is None
    report = json.loads(capsys.readouterr().out.strip())
    assert report["mode"] == "dry-run"
    assert report["pending_events"] == 1
    assert report["events"][0]["candidates"][0]["text"] == "Prefers round mugs."
    # Dry-run must not have moved or mutated the pending event.
    pending = list(runtime.pending_dir().glob("*.json"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text(encoding="utf-8"))["status"] == "pending"
    assert calls, "dry-run must contact the provider exactly for planning"


def test_extractor_confirm_adds_through_runtime_and_finalizes(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="I prefer round mugs", assistant="Noted.")
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [
                {"text": "Prefers round mugs.", "category": ["codex-auto"], "importance": 0.7},
                {"text": "values quiet rooms", "importance": 0.4},
            ]
        })}}]
    }]
    added, searched = [], []

    def fake_runtime(*argv, **kwargs):
        if argv and argv[0] == "add":
            added.append(argv[-1])
            return 0, json.dumps({"id": f"rec-{len(added)}"}), ""
        if argv and argv[0] == "search":
            searched.append(argv[-1])
            return 0, json.dumps({"memories": []}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["status"] == "extracted"
    assert added == ["Prefers round mugs.", "values quiet rooms"]
    event_file = next((runtime.extracted_dir()).glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    assert stored["status"] == "extracted"
    assert stored["candidates"][0]["record_id"] == "rec-1"
    assert len(stored["candidates"]) == 2
    assert not list(runtime.pending_dir().glob("*.json"))
    assert searched == ["Prefers round mugs.", "values quiet rooms"]


def test_extractor_confirm_dedupes_against_stored_text(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="same", assistant="same noted")
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{"text": "Prefers round mugs.", "importance": 0.6}]
        })}}]
    }]

    def fake_runtime(*argv, **kwargs):
        if argv and argv[0] == "search":
            return 0, json.dumps({"memories": [{"text": "Prefers round mugs."}]}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    added = []
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        _ = added
        cli.main(argv)
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["status"] == "extracted"
    event_file = next((runtime.extracted_dir()).glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    assert stored["skipped"] == [{"text": "Prefers round mugs.", "reason": "duplicate"}]
    assert stored["candidates"] == []


def test_extractor_rejects_secret_shaped_candidates(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [
                {"text": "sk-abcdefghijklmnopqrs123", "importance": 0.9},
                {"text": "keep this", "importance": 0.5},
            ]
        })}}]
    }]

    def fake_runtime(*argv, **kwargs):
        if argv and argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        if argv and argv[0] == "add":
            return 0, json.dumps({"id": "rec-1"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["rejected"], report
    event_files = list((runtime.extracted_dir()).glob("*.json")) + list(runtime.pending_dir().glob("*.json"))
    stored = json.loads(event_files[0].read_text(encoding="utf-8"))
    assert "sk-abcdefghijklmnopqrs123" not in json.dumps(stored)


def test_extractor_extraction_failure_leaves_event_pending(hook_env, monkeypatch, capsys):
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    # A malformed model reply must fail closed: event stays pending with an error.
    replies = [{"choices": [{"message": {"content": "gibberish-not-json"}}]}]
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["status"] == "pending"
    assert report["events"][0].get("extraction_error")
    event_file = next(runtime.pending_dir().glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    assert stored["status"] == "pending"
    assert stored.get("last_error")
    assert "gibberish-not-json" not in json.dumps(stored)  # error surfaced, not echoed


def test_extractor_records_rejections_and_never_adds(hook_env, monkeypatch, capsys):
    """All-rejected candidates terminate the event without any memory write."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    long_text = "y" * 300
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [
                {"text": long_text, "importance": 0.5},
                {"text": "valid", "importance": 0.5, "extra_key": True},
                {"text": "keeps", "importance": 1.4},
            ]
        })}}]
    }]
    attempted = []

    def fake_runtime(*argv, **kwargs):
        attempted.append(argv)
        if argv and argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        return 0, json.dumps({"id": "rec-x"}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    rejected = report["events"][0]["rejected"]
    assert len(rejected) >= 2, rejected
    assert report["events"][0]["status"] == "extracted"  # terminal, no re-extract loop
    assert report["events"][0]["admitted"] == []
    stored = json.loads(
        next((runtime.extracted_dir()).glob("*.json")).read_text(encoding="utf-8")
    )
    assert stored["candidates"] == []
    assert not any(argv and argv[0] == "add" for argv in attempted)


# --- Top-up: runtime helper errors + recall/capture edge branches ---


def test_call_runtime_surfaces_os_failure(hook_env, monkeypatch):
    runtime = load("lifecycle_runtime")

    def raise_os(*argv, **kwargs):
        raise FileNotFoundError("gone")

    monkeypatch.setattr(runtime, "subprocess", types.SimpleNamespace(run=raise_os))
    with pytest.raises(runtime.HookError, match="gone"):
        runtime.call_runtime("search", "--query", "x")


def test_call_runtime_surfaces_timeouts(hook_env, monkeypatch):
    import subprocess as real_subprocess

    runtime = load("lifecycle_runtime")

    def raise_timeout(*argv, **kwargs):
        raise real_subprocess.TimeoutExpired(cmd="rt", timeout=1)

    monkeypatch.setattr(runtime.subprocess, "run", raise_timeout)
    with pytest.raises(runtime.HookError, match="timed out"):
        runtime.call_runtime("search", "--query", "x")


def test_call_runtime_passes_direct_argv(hook_env, monkeypatch):
    runtime = load("lifecycle_runtime")
    seen = []

    def fake(argv, **kwargs):
        seen.append(argv)
        return types.SimpleNamespace(returncode=0, stdout='{"ok": 1}', stderr="")

    monkeypatch.setattr(runtime.subprocess, "run", fake)
    code = runtime.call_runtime("search", "--query", "x")
    assert code == (0, '{"ok": 1}', "")
    assert seen[0][1:3] == ["--home", str(runtime.profile_path())]
    assert "search" in seen[0]
    assert "--query" in seen[0]


def test_emit_with_only_system_message(hook_env, capsys):
    runtime = load("lifecycle_runtime")
    assert runtime.emit(system_message="note only") is None
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"systemMessage": "note only"}


def test_emit_both_context_and_message(hook_env, capsys):
    runtime = load("lifecycle_runtime")
    assert runtime.emit(additional_context="ctx", system_message="warn") is None
    payload = json.loads(capsys.readouterr().out)
    assert payload["systemMessage"] == "warn"
    assert payload["hookSpecificOutput"]["additionalContext"] == "ctx"


def test_read_hook_input_rejects_not_object(hook_env, monkeypatch):
    runtime = load("lifecycle_runtime")
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: "[1]")})())
    with pytest.raises(runtime.HookError, match="JSON object"):
        runtime.read_hook_input()


def test_read_hook_input_rejects_malformed(hook_env, monkeypatch):
    runtime = load("lifecycle_runtime")
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: "{oops")})())
    with pytest.raises(runtime.HookError, match="Invalid hook input"):
        runtime.read_hook_input()


def test_recall_query_fallback_for_root_path(monkeypatch):
    module = load("session_recall")
    assert module.recall_query({"cwd": "/"}) == "/"


def test_recall_misread_runtime_output(hook_env, monkeypatch, capsys):
    module = load("session_recall")
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    monkeypatch.setattr(module.runtime, "call_runtime", lambda *a, **k: (0, "not-json", ""))
    feed_stdin(monkeypatch, {"cwd": "/tmp/demo"})
    assert module.main() is None
    payload = json.loads(capsys.readouterr().out)
    assert "misread Runtime output" in payload["systemMessage"]


def test_recall_tolerates_wrong_shape(hook_env, monkeypatch, capsys):
    module = load("session_recall")
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    monkeypatch.setattr(module.runtime, "call_runtime", lambda *a, **k: (0, '{"nope": 1}', ""))
    feed_stdin(monkeypatch, {"cwd": "/tmp/shape"})
    assert module.main() is None
    assert capsys.readouterr().out == ""


def test_recall_truncates_long_context(hook_env, monkeypatch, capsys):
    module = load("session_recall")
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    feed_stdin(monkeypatch, {"cwd": "/tmp/demo"})

    def fake(*a, **k):
        rows = {"memories": [{"text": "z" * 4000}]}
        return 0, json.dumps(rows), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake)
    assert module.main() is None
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["hookSpecificOutput"]["additionalContext"]) <= module.runtime.DEFAULT_CONTEXT_CHARS


def test_remember_fullwidth_colon_is_matched(hook_env, monkeypatch, capsys):
    capture = load("user_prompt_capture")
    calls = []
    monkeypatch.setattr(
        capture.runtime,
        "call_runtime",
        lambda *a, **k: calls.append(a) or (0, "{\"id\": \"1\"}", ""),
    )
    monkeypatch.setattr(capture.runtime, "load_scope", lambda: ("u", "a"))
    feed_stdin(monkeypatch, {"prompt": "Remember：use warm mugs."})
    assert capture.main() is None
    _ = json.loads(capsys.readouterr().out)
    assert calls
    assert calls[0][-1] == "use warm mugs."


def test_capture_non_string_prompt_is_ignored(hook_env, monkeypatch, capsys):
    capture = load("user_prompt_capture")
    feed_stdin(monkeypatch, {"prompt": 42})
    assert capture.main() is None
    assert capsys.readouterr().out == ""


def test_capture_blank_prompt_is_ignored(hook_env, monkeypatch, capsys):
    capture = load("user_prompt_capture")
    feed_stdin(monkeypatch, {"prompt": "   "})
    assert capture.main() is None
    assert capsys.readouterr().out == ""


def test_capture_add_failure_surfaces(hook_env, monkeypatch, capsys):
    capture = load("user_prompt_capture")
    monkeypatch.setattr(capture.runtime, "call_runtime", lambda *a, **k: (2, "{}", "runtime down"))
    monkeypatch.setattr(capture.runtime, "load_scope", lambda: ("u", "a"))
    feed_stdin(monkeypatch, {"prompt": "Remember: keep it."})
    assert capture.main() is None
    assert "runtime down" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_capture_stage_write_failure_is_not_fatal(hook_env, monkeypatch):
    capture = load("user_prompt_capture")
    runtime = load("lifecycle_runtime")
    monkeypatch.setattr(runtime, "write_json_private", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    feed_stdin(monkeypatch, {"prompt": "whatever, no remember:"})
    assert capture.main() is None


def test_extract_provider_missing_key_header_is_empty_for_local(monkeypatch):
    cli = load("extract_pending")
    monkeypatch.delenv("EXTRACTION_API_KEY", raising=False)
    assert cli._extraction_key() == ""
    monkeypatch.setenv("EXTRACTION_API_KEY", "k-123")
    assert cli._extraction_key() == "k-123"


def test_extract_parse_model_json_tolerates_fences(monkeypatch):
    cli = load("extract_pending")
    document = cli._parse_model_json('```json\n{"memories": []}\n```')
    assert document == {"memories": []}
    with pytest.raises(ValueError):
        cli._parse_model_json('{"oops": 1}')


def test_extract_validate_bounds_categories_and_importance(monkeypatch):
    cli = load("extract_pending")
    good, rejected = cli.validate_candidates(
        {
            "memories": [
                {"text": "plain", "category": ["codex-auto", "project"], "importance": 0.5},
                {"text": "with long" + " y" * 300, "importance": 0.5},
                {"text": "bad type", "category": "project", "importance": 0.5},
                {"text": "range", "importance": 1.5},
            ]
        },
        {},
    )
    assert len(good) == 1
    assert good[0]["category"] == ["codex-auto", "project"]
    assert len(rejected) == 3


def test_extract_truncates_extra_candidates(monkeypatch):
    cli = load("extract_pending")
    good, rejected = cli.validate_candidates(
        {
            "memories": [
                {"text": f"number-{index}", "importance": 0.3} for index in range(5)
            ]
        },
        {},
    )
    assert [c["text"] for c in good] == ["number-0", "number-1", "number-2"]
    assert any("extra candidates dropped" in item for item in rejected)


def test_extract_redacts_environment_keys(monkeypatch):
    cli = load("extract_pending")
    monkeypatch.setenv("MY_SAMPLE_KEY", "topsecretvalue")
    assert "topsecretvalue" not in cli.redact("entered topsecretvalue here")
