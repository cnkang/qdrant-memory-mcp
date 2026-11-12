"""Optional lifecycle-mode hook handlers: released contract and safe behavior."""

import importlib.util
import json
import shutil
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
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
    assert capture.main() == 0


def test_user_prompt_submit_stages_scratch_and_honors_remember(hook_env, monkeypatch, capsys):
    """Verify UserPromptSubmit stages scratch and still saves a remember line."""
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
    assert call == [["add", "--text", " team offsite is in May."]]
    scratch = runtime.scratch_path_for("sess-1", "t-1")
    staged = json.loads(scratch.read_text(encoding="utf-8"))
    assert staged["session_id"] == "sess-1"
    assert staged["turn_id"] == "t-1"
    assert staged["user_excerpt"] == "Remember: team offsite is in May."


def test_auto_capture_opt_out_skips_prompt_staging(hook_env, monkeypatch, capsys):
    """Verify QDRANT_MEMORY_CODEX_AUTO_CAPTURE=0 disables prompt staging."""
    runtime = load("lifecycle_runtime")
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_AUTO_CAPTURE", "0")
    feed_stdin(monkeypatch, {"session_id": "sess-1", "turn_id": "t-1", "prompt": "plain question"})
    capture = load("user_prompt_capture")
    capture.main()
    assert not runtime.scratch_path_for("sess-1", "t-1").exists()
    assert capsys.readouterr().out == ""


def test_user_prompt_submit_scratch_records_excerpt(hook_env, monkeypatch):
    """Verify pairing scratch stores the bounded user excerpt."""
    stage_scratch(monkeypatch, load("lifecycle_runtime"))
    runtime = load("lifecycle_runtime")
    staged = json.loads(
        runtime.scratch_path_for("sess-1", "t-1").read_text(encoding="utf-8")
    )
    assert staged["user_excerpt"] == "plain question"
    assert staged["user_truncated"] is False
    assert staged["cwd"] == "/work"


def test_scratch_prefers_plugin_data_and_cleans(hook_env, monkeypatch, tmp_path):
    """Verify scratch prefers PLUGIN_DATA and is removed after pairing."""
    plugin_data = tmp_path / "plugin-data"
    monkeypatch.setenv("PLUGIN_DATA", str(plugin_data))
    runtime = load("lifecycle_runtime")
    stage_scratch(monkeypatch, runtime)
    staged = plugin_data / "turn_inputs"
    assert staged.is_dir()
    assert list(staged.glob("*.json"))
    assert not (runtime.events_root() / "scratch").exists()


def test_stop_capture_pairs_and_writes_bounded_pending_event(hook_env, monkeypatch, capsys):
    """Verify Stop capture pairs the turn and writes one bounded pending event."""
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
    """Verify one turn maps to one deterministic pending event."""
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
    """Verify assistant text is truncated at the configured byte bound."""
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
    """Verify Stop capture without pairing scratch captures nothing."""
    stop = load("turn_capture")
    runtime = load("lifecycle_runtime")
    feed_stdin(monkeypatch, {
        "session_id": "sess-2", "turn_id": "t-9",
        "last_assistant_message": "orphan assistant text",
    })
    assert stop.main() is None
    assert list(runtime.pending_dir().glob("*.json")) == []


def test_stop_capture_requires_assistant_text(hook_env, monkeypatch):
    """Verify a Stop event without assistant text captures nothing."""
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
    """Verify a full pending buffer pauses capture and reports overflow."""
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
    """Verify scratch pruning removes only expired entries."""
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
    """Stage one pending event for extractor tests."""
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


def test_owner_candidate_payload_contains_candidates_only():
    """Map extraction-v1 candidates without forwarding either turn transcript."""
    cli = extractor_cli()
    event = {
        "event_id": "codex-auto-synthetic",
        "session_id": "synthetic-session",
        "user_text": {"excerpt": "Synthetic raw user transcript"},
        "assistant_text": {"excerpt": "Synthetic raw assistant transcript"},
    }
    candidate = {
        "text": "Prefers round mugs.",
        "category": ["codex-auto"],
        "importance": 0.7,
        "replacement_intent": False,
    }
    payload, rejected = cli._owner_candidate_payload(event, [candidate])
    assert rejected == []
    assert payload == {
        "event_id": "codex-auto-synthetic",
        "session_id": "synthetic-session",
        "kind": "turn_completed",
        "candidate_schema": "qdrant-memory/extraction-v1",
        "candidates": [candidate],
    }
    assert "user_text" not in payload and "assistant_text" not in payload
    assert "scope" not in payload and "user_id" not in payload and "agent_id" not in payload


def test_owner_candidate_payload_rejects_ambiguous_replacements():
    """Owner's one replacement context cannot ambiguously cover several candidates."""
    cli = extractor_cli()
    event = {"event_id": "evt", "session_id": "sess"}
    replacement = {
        "text": "User now uses Neovim.",
        "category": ["preference"],
        "importance": 0.7,
        "replacement_intent": True,
        "replacement_context": "User uses Vim.",
    }
    payload, rejected = cli._owner_candidate_payload(event, [replacement, replacement])
    assert payload["candidates"] == []
    assert "replacement_context" not in payload
    assert len(rejected) == 1 and "one context per event" in rejected[0]


def test_owner_lifecycle_requires_https(hook_env, monkeypatch, capsys):
    """Reject an insecure Owner target before reading or submitting pending data."""
    cli = extractor_cli()
    with pytest.raises(SystemExit) as caught:
        cli.main([
            "--model", "fixture-extractor", "--confirm",
            "--owner-lifecycle-url", "http://owner.example",
        ])
    assert caught.value.code == 2
    assert "HTTPS" in capsys.readouterr().err


def test_owner_lifecycle_submits_candidates_over_stdin_only(
    hook_env, monkeypatch, capsys
):
    """The opt-in Owner route sends only validated candidates through Runtime stdin."""
    runtime = load("lifecycle_runtime")
    stage_pending(
        hook_env,
        monkeypatch,
        runtime,
        user="Synthetic raw user transcript: I prefer round mugs.",
        assistant="Synthetic raw assistant transcript: preference noted.",
    )
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{
                "text": "Prefers round mugs.",
                "category": ["codex-auto"],
                "importance": 0.7,
            }]
        })}}]
    }]
    seen = []
    monkeypatch.setenv("OWNER_TEST_TOKEN", "synthetic-owner-secret")

    def fake_runtime(*argv, **kwargs):
        assert argv[0] == "remote-event"
        assert "synthetic-owner-secret" not in argv
        action = argv[argv.index("--action") + 1]
        payload = json.loads(kwargs["input_text"])
        seen.append((action, argv, payload))
        return 0, json.dumps({"event_id": payload["event_id"], "status": (
            "NOT_FOUND" if action == "status" else "COMMITTED"
        )}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, provider_calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.extend([
            "--confirm", "--owner-lifecycle-url", "https://owner.example",
            "--owner-token-env", "OWNER_TEST_TOKEN",
        ])
        cli.main(argv)
        assert len(provider_calls) == 1
    report_text = capsys.readouterr().out
    report = json.loads(report_text)
    assert [item[0] for item in seen] == ["status", "submit"]
    submitted = seen[1][2]
    assert submitted["candidate_schema"] == "qdrant-memory/extraction-v1"
    assert submitted["candidates"][0]["text"] == "Prefers round mugs."
    assert "user" not in submitted and "assistant" not in submitted
    assert "user_text" not in submitted and "assistant_text" not in submitted
    assert "scope" not in submitted and "user_id" not in submitted
    assert "Synthetic raw" not in json.dumps(submitted)
    assert "synthetic-owner-secret" not in report_text
    assert report["events"][0]["status"] == "extracted"
    assert report["events"][0]["candidate_count"] == 1
    stored = json.loads(next(runtime.extracted_dir().glob("*.json")).read_text())
    assert stored["owner_lifecycle"]["status"] == "COMMITTED"
    assert stored["owner_lifecycle"]["candidate_sha256"]


def test_owner_lifecycle_retries_by_id_without_reextracting(
    hook_env, monkeypatch, capsys
):
    """A durable Owner retry sends only event_id and never reruns Ollama."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="Synthetic retry turn", assistant="Noted.")
    cli = extractor_cli()
    actions = []
    status_calls = 0

    def fake_runtime(*argv, **kwargs):
        nonlocal status_calls
        action = argv[argv.index("--action") + 1]
        payload = json.loads(kwargs["input_text"])
        actions.append((action, payload))
        if action == "status":
            status_calls += 1
            status = "NOT_FOUND" if status_calls == 1 else "PENDING"
        else:
            status = {"submit": "PENDING", "retry": "COMMITTED"}[action]
        return 0, json.dumps({"event_id": payload["event_id"], "status": status}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    replies = [{"choices": [{"message": {"content": json.dumps({
        "memories": [{"text": "Synthetic durable preference.", "importance": 0.6}]
    })}}]}]
    for server, provider_calls in extraction_provider_stub(monkeypatch, replies):
        base = extractor_args(monkeypatch, server.server_port)
        base.extend(["--confirm", "--owner-lifecycle-url", "https://owner.example"])
        cli.main(base)
        assert len(provider_calls) == 1
        base[base.index("--base-url") + 1] = "http://127.0.0.1:1/v1"
        capsys.readouterr()
        cli.main(base)
        assert len(provider_calls) == 1
    report = json.loads(capsys.readouterr().out)
    assert [item[0] for item in actions] == ["status", "submit", "status", "retry"], report
    assert actions[3][1] == {"event_id": actions[0][1]["event_id"]}
    assert report["events"][0]["status"] == "extracted"


@pytest.mark.parametrize(
    ("owner_status", "operator"),
    [("FAILED", "Runtime operator"), ("QUARANTINED", "Owner operator")],
)
def test_owner_manual_recovery_states_are_not_retried(
    hook_env, monkeypatch, owner_status, operator
):
    """Failed and quarantined Owner events stay pending for operator recovery."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="Synthetic quarantine turn", assistant="Noted.")
    cli = extractor_cli()
    event = cli.load_pending(mutate=False)[0][0]
    marker = {
        "event_id": event["event_id"],
        "source_sha256": cli._owner_source_digest(event),
        "candidate_sha256": "synthetic-candidate-hash",
        "status": "PENDING",
        "candidate_count": 1,
        "action": "submit",
        "updated_utc": "2026-11-12T00:00:00Z",
    }
    assert cli._persist_owner_intent(event, marker)
    actions = []

    def fake_runtime(*argv, **kwargs):
        action = argv[argv.index("--action") + 1]
        actions.append(action)
        payload = json.loads(kwargs["input_text"])
        return 0, json.dumps({"event_id": payload["event_id"], "status": owner_status}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    result = cli.admit_owner_all(
        cli.load_pending(mutate=False)[0], None, url="https://owner.example",
        token_env="OWNER_TEST_TOKEN", ca_file=None,
    )
    assert actions == ["status"]
    assert result["events"][0]["status"] == "pending"
    assert result["events"][0]["owner_status"] == owner_status
    assert operator in result["events"][0]["last_error"]


def test_owner_malformed_status_receipt_stays_pending(hook_env, monkeypatch):
    """An invalid remote status is rejected without echoing the response."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="Synthetic malformed status", assistant="Noted.")
    cli = extractor_cli()

    def fake_runtime(*argv, **kwargs):
        payload = json.loads(kwargs["input_text"])
        return 0, json.dumps({"event_id": payload["event_id"], "status": ["synthetic-secret"]}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    result = cli.admit_owner_all(
        cli.load_pending(mutate=False)[0], None, url="https://owner.example",
        token_env="OWNER_TEST_TOKEN", ca_file=None,
    )
    assert result["events"][0]["status"] == "pending"
    assert result["events"][0]["last_error"] == "Owner lifecycle returned an invalid receipt"
    assert "synthetic-secret" not in json.dumps(result)


def test_owner_malformed_local_receipt_stays_pending_without_request(
    hook_env, monkeypatch
):
    """Corrupted local Owner metadata is kept for review instead of crashing."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, user="Synthetic malformed receipt", assistant="Noted.")
    cli = extractor_cli()
    event = cli.load_pending(mutate=False)[0][0]
    marker = {
        "event_id": event["event_id"],
        "source_sha256": cli._owner_source_digest(event),
        "status": "PENDING",
        "candidate_count": "not-an-integer",
        "action": "submit",
    }
    assert cli._persist_owner_intent(event, marker)
    calls = []
    monkeypatch.setattr(runtime, "call_runtime", lambda *args, **kwargs: calls.append(args))
    result = cli.admit_owner_all(
        cli.load_pending(mutate=False)[0], None, url="https://owner.example",
        token_env="OWNER_TEST_TOKEN", ca_file=None,
    )
    assert calls == []
    assert result["events"][0]["status"] == "pending"
    assert result["events"][0]["candidate_count"] == 0
    assert "malformed" in result["events"][0]["last_error"]


def test_owner_receipt_survives_redelivery_and_changed_snapshot_stays_pending(
    hook_env, monkeypatch
):
    """A newer Stop snapshot cannot inherit a commit for the older turn content."""
    runtime = load("lifecycle_runtime")
    stage_pending(
        hook_env, monkeypatch, runtime, user="Synthetic old user turn",
        assistant="Synthetic old assistant turn", session="sess-owner", turn="turn-owner",
    )
    cli = extractor_cli()
    event = cli.load_pending(mutate=False)[0][0]
    original_digest = cli._owner_source_digest(event)
    marker = {
        "event_id": event["event_id"],
        "source_sha256": original_digest,
        "candidate_sha256": "synthetic-candidate-hash",
        "status": "COMMITTED",
        "candidate_count": 1,
        "action": "submit",
        "updated_utc": "2026-11-12T00:00:00Z",
    }
    assert cli._persist_owner_intent(event, marker)
    stage_pending(
        hook_env, monkeypatch, runtime, user="Synthetic edited user turn",
        assistant="Synthetic edited assistant turn", session="sess-owner", turn="turn-owner",
    )
    updated = cli.load_pending(mutate=False)[0][0]
    assert updated["owner_lifecycle"] == marker
    calls = []
    monkeypatch.setattr(runtime, "call_runtime", lambda *args, **kwargs: calls.append(args))
    first = cli.admit_owner_all(
        [updated], None, url="https://owner.example",
        token_env="OWNER_TEST_TOKEN", ca_file=None,
    )
    second = cli.admit_owner_all(
        cli.load_pending(mutate=False)[0], None, url="https://owner.example",
        token_env="OWNER_TEST_TOKEN", ca_file=None,
    )
    assert first["events"][0]["status"] == "pending"
    assert second["events"][0]["status"] == "pending"
    assert "earlier snapshot" in first["events"][0]["last_error"]
    assert calls == []
    stored = json.loads(next(runtime.pending_dir().glob("*.json")).read_text())
    assert stored["owner_lifecycle"] == marker


def test_extractor_dry_run_lists_candidates_without_writes(hook_env, monkeypatch, capsys):
    """Verify the default extractor run is a dry-run with zero writes."""
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
    """Verify confirm admits candidates through Runtime and finalizes the event."""
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
    """Verify confirm skips a candidate already present in the profile."""
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
    """Verify secret-shaped candidates are rejected before admission."""
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
    """Verify an extraction failure keeps the event pending with an error."""
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


def test_extractor_empty_choices_leaves_event_pending(hook_env, monkeypatch, capsys):
    """Verify an empty provider choice list stays a per-event error."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    replies = [{"choices": []}]
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        cli.main(argv)

    event_file = next(runtime.pending_dir().glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    assert stored["status"] == "pending"
    assert stored.get("last_error") == "extraction response lacks message content"


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
    """Verify the Runtime CLI receives the prepared argument vector directly."""
    runtime = load("lifecycle_runtime")
    seen = []

    def fake(argv, **kwargs):
        seen.append((argv, kwargs))
        return types.SimpleNamespace(returncode=0, stdout='{"ok": 1}', stderr="")

    monkeypatch.setattr(runtime.subprocess, "run", fake)
    code = runtime.call_runtime(
        "remote-event", "--action", "status", input_text='{"event_id":"synthetic"}'
    )
    assert code == (0, '{"ok": 1}', "")
    argv, kwargs = seen[0]
    assert argv[1:3] == ["--home", str(runtime.profile_path())]
    assert "remote-event" in argv
    assert "event_id" not in " ".join(argv)
    assert kwargs["input"] == '{"event_id":"synthetic"}'


def test_emit_with_only_system_message(hook_env, capsys):
    """Verify emit with only a system message stays silent to the model."""
    runtime = load("lifecycle_runtime")
    assert runtime.emit(system_message="note only") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"systemMessage": "note only"}


def test_emit_both_context_and_message(hook_env, capsys):
    """Verify emit can return context and a system message together."""
    runtime = load("lifecycle_runtime")
    assert runtime.emit(additional_context="ctx", system_message="warn") == 0
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
    """Verify recall falls back to the full path for a root working directory."""
    module = load("session_recall")
    assert module.recall_query({"cwd": "/"}) == "/"


def test_recall_misread_runtime_output(hook_env, monkeypatch, capsys):
    """Verify recall reports unreadable Runtime output gracefully."""
    module = load("session_recall")
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    monkeypatch.setattr(module.runtime, "call_runtime", lambda *a, **k: (0, "not-json", ""))
    feed_stdin(monkeypatch, {"cwd": "/tmp/demo"})
    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert "misread Runtime output" in payload["systemMessage"]


def test_recall_tolerates_wrong_shape(hook_env, monkeypatch, capsys):
    """Verify recall stays silent for an unexpected payload shape."""
    module = load("session_recall")
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    monkeypatch.setattr(module.runtime, "call_runtime", lambda *a, **k: (0, '{"nope": 1}', ""))
    feed_stdin(monkeypatch, {"cwd": "/tmp/shape"})
    assert module.main() == 0
    assert capsys.readouterr().out == ""


def test_recall_truncates_long_context(hook_env, monkeypatch, capsys):
    """Verify recall truncates additional context to the configured limit."""
    module = load("session_recall")
    monkeypatch.setattr(module.runtime, "load_scope", lambda: ("u", "a"))
    feed_stdin(monkeypatch, {"cwd": "/tmp/demo"})

    def fake(*a, **k):
        rows = {"memories": [{"text": "z" * 4000}]}
        return 0, json.dumps(rows), ""

    monkeypatch.setattr(module.runtime, "call_runtime", fake)
    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["hookSpecificOutput"]["additionalContext"]) <= module.runtime.DEFAULT_CONTEXT_CHARS


def test_remember_fullwidth_colon_is_matched(hook_env, monkeypatch, capsys):
    """Verify the full-width colon form of remember is honored."""
    capture = load("user_prompt_capture")
    calls = []
    monkeypatch.setattr(
        capture.runtime,
        "call_runtime",
        lambda *a, **k: calls.append(a) or (0, "{\"id\": \"1\"}", ""),
    )
    monkeypatch.setattr(capture.runtime, "load_scope", lambda: ("u", "a"))
    feed_stdin(monkeypatch, {"prompt": "Remember：use warm mugs."})
    assert capture.main() == 0
    _ = json.loads(capsys.readouterr().out)
    assert calls
    assert calls[0][-1] == "use warm mugs."


def test_capture_non_string_prompt_is_ignored(hook_env, monkeypatch, capsys):
    """Verify a non-string prompt is ignored by the capture hook."""
    capture = load("user_prompt_capture")
    feed_stdin(monkeypatch, {"prompt": 42})
    assert capture.main() == 0
    assert capsys.readouterr().out == ""


def test_capture_blank_prompt_is_ignored(hook_env, monkeypatch, capsys):
    """Verify a blank prompt is ignored by the capture hook."""
    capture = load("user_prompt_capture")
    feed_stdin(monkeypatch, {"prompt": "   "})
    assert capture.main() == 0
    assert capsys.readouterr().out == ""


def test_capture_add_failure_surfaces(hook_env, monkeypatch, capsys):
    """Verify a failed Runtime add is surfaced as a diagnostic."""
    capture = load("user_prompt_capture")
    monkeypatch.setattr(capture.runtime, "call_runtime", lambda *a, **k: (2, "{}", "runtime down"))
    monkeypatch.setattr(capture.runtime, "load_scope", lambda: ("u", "a"))
    feed_stdin(monkeypatch, {"prompt": "Remember: keep it."})
    assert capture.main() == 0
    assert "runtime down" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_capture_stage_write_failure_is_not_fatal(hook_env, monkeypatch):
    """Verify a staging write failure never blocks the prompt."""
    capture = load("user_prompt_capture")
    runtime = load("lifecycle_runtime")
    monkeypatch.setattr(runtime, "write_json_private", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    feed_stdin(monkeypatch, {"prompt": "whatever, no remember:"})
    assert capture.main() == 0


def test_extract_provider_missing_key_header_is_empty_for_local(monkeypatch):
    """Verify a local endpoint sends no empty Authorization header."""
    cli = load("extract_pending")
    monkeypatch.delenv("EXTRACTION_API_KEY", raising=False)
    assert cli._extraction_key() == ""
    monkeypatch.setenv("EXTRACTION_API_KEY", "k-123")
    assert cli._extraction_key() == "k-123"


def test_extract_parse_model_json_tolerates_fences(monkeypatch):
    """Verify model JSON wrapped in code fences is parsed."""
    cli = load("extract_pending")
    document = cli._parse_model_json('```json\n{"memories": []}\n```')
    assert document == {"memories": []}
    with pytest.raises(ValueError):
        cli._parse_model_json('{"oops": 1}')


def test_extract_validate_bounds_categories_and_importance(monkeypatch):
    """Verify candidate validation enforces bounds, categories and importance."""
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
    """Verify candidates beyond the per-turn cap are dropped."""
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
    """Verify environment secret values are redacted from diagnostics."""
    cli = load("extract_pending")
    monkeypatch.setenv("MY_SAMPLE_KEY", "topsecretvalue")
    assert "topsecretvalue" not in cli.redact("entered topsecretvalue here")


# --- Review hardening: credentials, consent, concurrency, receipts ---


def test_candidate_validation_rejects_new_credential_formats(monkeypatch):
    """Bearer tokens, PATs, Slack tokens, PEM blocks and password= are refused."""
    cli = load("extract_pending")
    secrets = [
        "github_pat_11ABCDEFGH2abcdefgh3xyzKey99",
        "xoxb-1234567890abcdef",
        "bearer AbcDef1234567890abcdef",
        "-----BEGIN PRIVATE KEY-----\\nMIIE",
        "password=hunter2secret",
        "AUTH: $EXTRACTION_API_KEY",
    ]
    for text in secrets:  # one candidate at a time: the contract caps batches at 3
        good, rejected = cli.validate_candidates(
            {"memories": [{"text": text, "importance": 0.5}]}, {}
        )
        assert good == []
        assert rejected == ["candidate looks secret-shaped"], text


def test_extraction_provider_uses_private_opener(hook_env, monkeypatch):
    """Ignore environment proxies and refuse redirects before sending data."""
    cli = load("extract_pending")
    proxy_handlers = [
        handler
        for handler in cli._OPENER.handlers
        if isinstance(handler, cli.urllib.request.ProxyHandler)
    ]
    # urllib omits an empty ProxyHandler from OpenerDirector.handlers, but
    # passing ProxyHandler({}) to build_opener suppresses the default
    # environment-backed proxy handler.
    assert all(not handler.proxies for handler in proxy_handlers)
    redirect_handler = next(
        handler
        for handler in cli._OPENER.handlers
        if isinstance(handler, cli._NoRedirect)
    )
    assert [
        handler
        for handler in cli._OPENER.handlers
        if isinstance(handler, cli.urllib.request.HTTPRedirectHandler)
    ] == [redirect_handler]

    request = cli.urllib.request.Request(
        "https://provider.example/v1/chat/completions",
        data=b"private staged text",
        headers={"Authorization": "Bearer test-key"},
        method="POST",
    )
    with pytest.raises(cli.urllib.error.HTTPError) as error:
        redirect_handler.redirect_request(
            request, None, 302, "Found", {}, "http://attacker.example/collect"
        )
    assert error.value.code == 302

    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, limit):
            assert limit == cli.MAX_RESPONSE_BYTES + 1
            body = {
                "choices": [
                    {"message": {"content": json.dumps({"memories": []})}}
                ]
            }
            return json.dumps(body).encode()

    def open_request(req, timeout):
        sent.append((req, timeout))
        return Response()

    monkeypatch.setattr(cli._OPENER, "open", open_request)
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("default opener must not be used"),
    )
    provider = cli.ExtractionProvider("http://127.0.0.1:11434/v1", "m")
    assert provider.extract("prompt") == {"memories": []}
    assert len(sent) == 1
    assert sent[0][0].full_url == "http://127.0.0.1:11434/v1/chat/completions"
    assert sent[0][1] == 60.0


def test_non_loopback_plaintext_endpoints_are_refused(hook_env):
    """HTTPS is mandatory before any staged text reaches a remote endpoint."""
    cli = load("extract_pending")
    with pytest.raises(ValueError, match="https"):
        cli.ExtractionProvider("http://example.com/v1", "m")
    with pytest.raises(ValueError, match="https"):
        cli.ExtractionProvider("http://10.1.2.3:8000/v1", "m")
    assert cli.ExtractionProvider("https://example.com/v1", "m").base_url
    assert cli.ExtractionProvider("http://127.0.0.1:11434/v1", "m").base_url
    assert cli.ExtractionProvider("http://localhost:11434/v1", "m").base_url


def test_main_refuses_unsafe_endpoints_before_any_send(hook_env, monkeypatch, capsys):
    """Verify unsafe extraction endpoints are rejected before any send."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    sent = []
    monkeypatch.setattr(
        cli._OPENER,
        "open",
        lambda *a, **k: sent.append(a)
        or (_ for _ in ()).throw(AssertionError("network send")),
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--base-url", "http://example.com/v1", "--model", "m"])
    assert exit_info.value.code == 2
    error = json.loads(capsys.readouterr().err.strip())
    assert "https" in error["error"]
    assert sent == []


def test_endpoint_loopback_check_uses_ip_parsing():
    """Verify DNS names starting with 127 are not treated as loopback."""
    cli = extractor_cli()
    assert cli._endpoint_is_loopback("http://127.0.0.1:11434/v1")
    assert cli._endpoint_is_loopback("http://[::1]:11434/v1")
    assert cli._endpoint_is_loopback("http://localhost:11434/v1")
    assert not cli._endpoint_is_loopback("http://127.attacker.example/v1")


class _RecordingProvider:
    """Stands in for ExtractionProvider without touching the network."""

    calls: list = []

    def __init__(self, base_url, model, timeout=60.0):
        self.base_url = base_url

    def extract(self, prompt):
        _RecordingProvider.calls.append(prompt)
        return {"memories": []}


def test_dry_run_never_sends_to_remote_providers(hook_env, monkeypatch, capsys):
    """Remote extraction requires the --confirm invocation as consent."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    monkeypatch.setattr(_RecordingProvider, "calls", [])
    monkeypatch.setattr(cli, "ExtractionProvider", _RecordingProvider)
    argv = ["--base-url", "https://remote.example/v1", "--model", "m", "--limit", "5"]
    cli.main(argv)
    report = json.loads(capsys.readouterr().out.strip())
    assert _RecordingProvider.calls == []
    assert "--confirm" in report["events"][0]["extraction_error"]
    assert list(runtime.pending_dir().glob("*.json"))  # event untouched
    cli.main([*argv, "--confirm"])
    assert len(_RecordingProvider.calls) == 1  # consent given, provider contacted


def test_build_prompt_rejects_malformed_nested_fields(hook_env):
    """Verify malformed nested event fields are rejected before prompting."""
    cli = extractor_cli()
    with pytest.raises(ValueError, match="user_text"):
        cli.build_prompt({"user_text": "a string"})
    with pytest.raises(ValueError, match="assistant_text"):
        cli.build_prompt({"user_text": {"excerpt": "ok"}, "assistant_text": 7})
    with pytest.raises(ValueError, match="user_text"):
        cli.build_prompt({})


def test_build_prompt_limits_replacement_intent_to_explicit_corrections(hook_env):
    """Replacement metadata must not be inferred from first mentions."""
    prompt = extractor_cli().build_prompt(
        {
            "user_text": {"excerpt": "The database is PostgreSQL 16."},
            "assistant_text": {"text": "Understood."},
        }
    )
    assert "replacement_intent is false by default" in prompt
    assert "Never set it for first mentions, restatements, or unchanged facts" in prompt
    normalized_prompt = " ".join(prompt.split())
    assert "content the user explicitly says not to remember or store" in normalized_prompt
    assert "Each replacement candidate must have its own context" in normalized_prompt
    assert "never reuse context across candidates" in normalized_prompt
    assert "Do not infer conflicts with memories that are not present in this turn" in normalized_prompt


def test_replacement_metadata_must_be_typed_bounded_and_secret_free(hook_env):
    """Replacement evidence is untrusted model output and stays bounded."""
    cli = extractor_cli()
    cases = [
        ({"text": "A durable fact.", "replacement_intent": "false"}, "replacement intent invalid"),
        ({"text": "A durable fact.", "replacement_intent": True, "replacement_context": 42}, "replacement context invalid"),
        ({"text": "A durable fact.", "replacement_intent": True, "replacement_context": "x" * 301}, "replacement context too long"),
        ({"text": "A durable fact.", "replacement_intent": True, "replacement_context": "sk-abcdefghijklmnopqrs123"}, "replacement context looks secret-shaped"),
        ({"text": "A durable fact.", "replacement_intent": False, "replacement_context": "old value"}, "replacement context without replacement intent"),
    ]
    for candidate, expected in cases:
        assert cli._candidate_error(candidate) == expected


def test_replacement_context_must_be_an_exact_user_input_substring(hook_env):
    """Assistant-only and invented text cannot authorize a replacement target."""
    cli = extractor_cli()
    event = {
        "user_text": {
            "excerpt": "The database was SQLite, but it is now PostgreSQL 16."
        },
        "assistant_text": {"text": "The timezone was PST."},
    }
    exact, exact_rejected = cli.validate_candidates(
        {
            "memories": [
                {
                    "text": "The database is PostgreSQL 16.",
                    "replacement_intent": True,
                    "replacement_context": "database was SQLite",
                }
            ]
        },
        event,
    )
    assert [candidate["replacement_context"] for candidate in exact] == [
        "database was SQLite"
    ]
    assert exact_rejected == []

    for context in ("timezone was PST", "favorite color was green"):
        good, rejected = cli.validate_candidates(
            {
                "memories": [
                    {
                        "text": "The timezone is UTC.",
                        "replacement_intent": True,
                        "replacement_context": context,
                    }
                ]
            },
            event,
        )
        assert good == []
        assert rejected == ["replacement context not present in user input"]


def test_prompt_and_validation_surface_truncation(hook_env):
    """Verify truncated inputs are surfaced to extraction and validation."""
    cli = extractor_cli()
    event = {
        "user_text": {"excerpt": "long user prompt", "truncated": True},
        "assistant_text": {"text": "long reply", "truncated": False},
    }
    prompt = cli.build_prompt(event)
    assert prompt.count("[TRUNCATED]") == 1
    assert "TRUNCATED input" in prompt
    # Only BOTH sides clipped triggers the hard admission guard.
    document = {"memories": [{"text": "some fact", "importance": 0.5}]}
    good, rejected = cli.validate_candidates(document, event)
    assert len(good) == 1
    assert rejected == []
    both = dict(event)
    both["assistant_text"] = {"text": "long reply", "truncated": True}
    good, rejected = cli.validate_candidates(document, both)
    assert good == []
    assert rejected == ["candidate not admitted: event inputs truncated"]


def test_extreme_importance_is_rejected_not_fatal(hook_env):
    """Verify an out-of-range importance is rejected without aborting the batch."""
    cli = extractor_cli()
    good, rejected = cli.validate_candidates(
        {"memories": [{"text": "big", "importance": 10**400}]}, {}
    )
    assert good == []
    assert rejected == ["candidate importance invalid"]


def test_malformed_choice_entries_are_per_event_errors(hook_env):
    """Verify malformed provider choice entries stay per-event errors."""
    cli = extractor_cli()
    with pytest.raises(ValueError, match="malformed choice"):
        cli._response_content({"choices": [None]})
    with pytest.raises(ValueError, match="not an object"):
        cli._response_content(["nope"])
    with pytest.raises(ValueError, match="lacks message content"):
        cli._response_content({"choices": [{"message": {}}]})
    assert cli._response_content({"choices": [{"message": {"content": "ok"}}]}) == "ok"


def test_oversized_provider_responses_are_refused(hook_env, monkeypatch, capsys):
    """Verify oversized provider responses are refused before parsing."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    replies = [
        {
            "choices": [
                {"message": {"content": "x" * (cli.MAX_RESPONSE_BYTES + 1024)}}
            ]
        }
    ]
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        cli.main(argv)
    report = json.loads(capsys.readouterr().out.strip())
    assert "exceeds" in report["events"][0]["extraction_error"]
    stored = json.loads(next(runtime.pending_dir().glob("*.json")).read_text(encoding="utf-8"))
    assert stored["status"] == "pending"


def test_hook_errors_during_confirm_do_not_abort_the_batch(hook_env, monkeypatch, capsys):
    """Verify a HookError in confirm is recorded without aborting later events."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, session="sess-1", turn="t-1")
    stage_pending(hook_env, monkeypatch, runtime, session="sess-2", turn="t-2")
    cli = extractor_cli()
    replies = [
        {"choices": [{"message": {"content": json.dumps({"memories": [{"text": "alpha fact", "importance": 0.5}]})}}]},
        {"choices": [{"message": {"content": json.dumps({"memories": [{"text": "beta fact", "importance": 0.5}]})}}]},
    ]

    def fake_runtime(*argv, **kwargs):
        if argv[0] == "search" and argv[-1] == "alpha fact":
            raise runtime.HookError("runtime gone")
        if argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-1"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    statuses = {event["status"] for event in report["events"]}
    assert statuses == {"pending", "extracted"}
    failed = next(event for event in report["events"] if event["status"] == "pending")
    assert "runtime gone" in failed["last_error"]
    done = next(event for event in report["events"] if event["status"] == "extracted")
    assert done["admitted"] == ["beta fact"]


def test_admission_retries_preserve_earlier_receipts(hook_env, monkeypatch, capsys):
    """Verify retries keep earlier admitted receipts and record IDs."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [
                {"text": "Prefers round mugs.", "importance": 0.7},
                {"text": "values quiet rooms", "importance": 0.4},
            ]
        })}}]
    }]

    def failing_second_add(*argv, **kwargs):
        if argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-1"}), ""  # first add succeeds

    def fake_runtime_first(*argv, **kwargs):
        if argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add" and argv[-1] == "values quiet rooms":
            return 1, "", "runtime exploded"
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-1"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime_first)
    for server, _calls in extraction_provider_stub(monkeypatch, [dict(replies[0])]):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    first_report = json.loads(capsys.readouterr().out.strip())
    assert first_report["events"][0]["status"] == "pending"
    pending_file = next(runtime.pending_dir().glob("*.json"))
    stored = json.loads(pending_file.read_text(encoding="utf-8"))
    assert [item["record_id"] for item in stored["candidates"]] == ["rec-1"]
    assert stored["attempts"] == 1

    def fake_runtime_retry(*argv, **kwargs):
        if argv[0] == "search":
            if argv[-1] == "Prefers round mugs.":
                return 0, json.dumps({"memories": [{"text": "Prefers round mugs."}]}), ""
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-2"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime_retry)
    for server, _calls in extraction_provider_stub(monkeypatch, [dict(replies[0])]):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    retry_report = json.loads(capsys.readouterr().out.strip())
    assert retry_report["events"][0]["status"] == "extracted"
    event_file = next(runtime.extracted_dir().glob("*.json"))
    final = json.loads(event_file.read_text(encoding="utf-8"))
    assert [item["record_id"] for item in final["candidates"]] == ["rec-1", "rec-2"]
    assert final["skipped"] == [
        {"text": "Prefers round mugs.", "reason": "already admitted"}
    ]
    assert "last_error" not in final  # the retry resolved the failure
    assert "attempts" not in final


def test_replacement_intent_deletes_the_superseded_record(hook_env, monkeypatch, capsys):
    """Verify a replacement deletes the superseded record only with explicit approval."""
    runtime = load("lifecycle_runtime")
    stage_pending(
        hook_env,
        monkeypatch,
        runtime,
        user="The old fact was 'prefers light mode'; now I prefer dark mode.",
    )
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{
                "text": "Prefers dark mode.", "category": ["codex-auto"],
                "importance": 0.6, "replacement_intent": True,
                "replacement_context": "prefers light mode",
            }],
        })}}]
    }]
    calls = []

    def fake_runtime(*argv, **kwargs):
        calls.append(argv)
        if argv[0] == "search":
            if argv[-1] == "prefers light mode":
                return 0, json.dumps({"memories": [{"id": "old-1", "text": "Prefers light mode."}]}), ""
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-9"}), ""
        if argv[0] == "delete":
            return 0, json.dumps({"id": argv[-1]}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.extend(["--confirm", "--allow-replacement-deletes"])
        assert cli.main(argv) is None
    assert ("delete", "--id", "old-1") in calls
    event_file = next(runtime.extracted_dir().glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    receipt = stored["candidates"][0]
    assert receipt["record_id"] == "rec-9"
    assert receipt["importance"] == 0.6
    assert receipt["provenance"]["capture_source"] == "codex-hook"
    assert receipt["replacement"]["deleted"] is True
    assert receipt["replacement"]["proposed_record_id"] == "old-1"
    assert receipt["replacement"]["proposed_text"] == "Prefers light mode."


def test_replacement_deletion_requires_explicit_approval(hook_env, monkeypatch, capsys):
    """Without the flag the located target is recorded as a proposal only."""
    runtime = load("lifecycle_runtime")
    stage_pending(
        hook_env,
        monkeypatch,
        runtime,
        user="The old fact was 'prefers light mode'; now I prefer dark mode.",
    )
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{
                "text": "Prefers dark mode.", "replacement_intent": True,
                "replacement_context": "prefers light mode",
            }],
        })}}]
    }]
    calls = []

    def fake_runtime(*argv, **kwargs):
        calls.append(argv)
        if argv[0] == "search":
            if argv[-1] == "prefers light mode":
                return 0, json.dumps({"memories": [{"id": "old-1", "text": "Prefers light mode."}]}), ""
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-1"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    assert not any(argv[0] == "delete" for argv in calls)  # nothing deleted
    event_file = next(runtime.extracted_dir().glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    receipt = stored["candidates"][0]
    assert receipt["replacement"]["target_found"] is True
    assert receipt["replacement"]["proposed_record_id"] == "old-1"
    assert "deleted" not in receipt["replacement"]
    assert "--allow-replacement-deletes" in receipt["replacement"]["note"]


def test_replacement_delete_hookerror_preserves_the_admitted_receipt(
    hook_env, monkeypatch, capsys
):
    """A failed delete after a successful add never loses the record receipt."""
    runtime = load("lifecycle_runtime")
    stage_pending(
        hook_env,
        monkeypatch,
        runtime,
        user="The old fact was 'prefers light mode'; now I prefer dark mode.",
    )
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{
                "text": "Prefers dark mode.", "replacement_intent": True,
                "replacement_context": "prefers light mode",
            }],
        })}}]
    }]

    def fake_runtime(*argv, **kwargs):
        if argv[0] == "search":
            if argv[-1] == "prefers light mode":
                return 0, json.dumps({"memories": [{"id": "old-1", "text": "Prefers light mode."}]}), ""
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-7"}), ""
        if argv[0] == "delete":
            raise runtime.HookError("runtime gone during delete")
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.extend(["--confirm", "--allow-replacement-deletes"])
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["status"] == "pending"
    assert "runtime gone during delete" in report["events"][0]["last_error"]
    stored = json.loads(next(runtime.pending_dir().glob("*.json")).read_text(encoding="utf-8"))
    receipt = stored["candidates"][0]  # the admitted receipt survived
    assert receipt["record_id"] == "rec-7"
    assert receipt["replacement"]["delete_error"] == "runtime gone during delete"


def test_multiple_replacements_keep_their_own_search_context(hook_env, monkeypatch):
    """Each correction must search for its own superseded fact."""
    runtime = load("lifecycle_runtime")
    stage_pending(
        hook_env,
        monkeypatch,
        runtime,
        user=(
            "The database was SQLite and the service timezone was PST. "
            "Now the database is PostgreSQL 16 and the timezone is UTC."
        ),
    )
    cli = extractor_cli()
    old_facts = ["database was SQLite", "service timezone was PST"]
    replies = [{
        "choices": [{"message": {"content": json.dumps({"memories": [
            {
                "text": "The database is PostgreSQL 16.",
                "replacement_intent": True,
                "replacement_context": old_facts[0],
            },
            {
                "text": "The service timezone is UTC.",
                "replacement_intent": True,
                "replacement_context": old_facts[1],
            },
        ]})}}]
    }]
    search_queries = []

    def fake_runtime(*argv, **kwargs):
        if argv[0] == "search":
            query = argv[-1]
            if query in old_facts:
                search_queries.append(query)
                index = old_facts.index(query)
                return 0, json.dumps({"memories": [{
                    "id": f"old-{index + 1}", "text": query,
                }]}), ""
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "new-record"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    assert search_queries == old_facts


def test_finalize_keeps_newer_content_pending_with_receipts(hook_env, monkeypatch):
    """A Stop redelivery during processing is never stamped with old status."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    pending_file = next(runtime.pending_dir().glob("*.json"))
    newer = json.loads(pending_file.read_text(encoding="utf-8"))
    newer["assistant_text"]["text"] = "redelivered newer reply"
    runtime.write_json_private(pending_file, newer)
    event_state = {
        "event_id": "older-run",
        "admitted": [{
            "text": "old fact", "record_id": "rec-1", "category": ["codex-auto"],
            "importance": 0.5, "replacement_intent": False,
        }],
        "skipped": [{"text": "old fact", "reason": "duplicate"}],
        "rejected": ["candidate looks secret-shaped"],
    }
    cli.finalize_event(
        pending_file, event_state, "extracted", loaded_fingerprint="loaded-digest"
    )
    stored = json.loads(pending_file.read_text(encoding="utf-8"))
    assert pending_file.parent == runtime.pending_dir()  # never moved
    assert stored["status"] == "pending"  # newer content stays pending
    assert "redelivered newer reply" in stored["assistant_text"]["text"]
    assert "processed_utc" not in stored  # newer turn was not marked processed
    assert [item["record_id"] for item in stored["candidates"]] == ["rec-1"]
    assert stored["skipped"] == [{"text": "old fact", "reason": "duplicate"}]
    assert stored["rejected"] == ["candidate looks secret-shaped"]
    # The unchanged-snapshot path still finalizes normally.
    current_fingerprint = runtime.file_fingerprint(pending_file)
    cli.finalize_event(
        pending_file,
        event_state,
        "extracted",
        loaded_fingerprint=current_fingerprint,
    )
    assert next(runtime.extracted_dir().glob(pending_file.name)).exists()
    assert not pending_file.exists()


def test_retry_skips_candidates_already_in_receipts(hook_env, monkeypatch):
    """Verify a retry does not re-add a candidate its event already admitted."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    pending_file = next(runtime.pending_dir().glob("*.json"))
    event = json.loads(pending_file.read_text(encoding="utf-8"))
    event["candidates"] = [{"text": "Prefers round mugs.", "record_id": "rec-1"}]
    pending_file.write_text(json.dumps(event), encoding="utf-8")
    outcome = {
        "_path": pending_file,
        "_fingerprint": runtime.file_fingerprint(pending_file),
        "event_id": event["event_id"],
        "candidates": [
            {
                "text": "Prefers round mugs.",
                "category": ["codex-auto"],
                "importance": 0.5,
                "replacement_intent": False,
            }
        ],
        "rejected": [],
    }
    calls = []

    def admit(*args, **kwargs):
        calls.append(args)
        return 0, "{}", ""

    result = cli._admit_event(outcome, admit)
    assert calls == []
    assert result["skipped"] == [
        {"text": "Prefers round mugs.", "reason": "already admitted"}
    ]


def test_replacement_without_context_is_recorded(hook_env, monkeypatch, capsys):
    """Verify a replacement without context is recorded without deleting anything."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{"text": "Prefers dark mode.", "replacement_intent": True}]
        })}}]
    }]
    calls = []

    def fake_runtime(*argv, **kwargs):
        calls.append(argv)
        if argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        if argv[0] == "add":
            return 0, json.dumps({"id": "rec-1"}), ""
        return 0, "{}", ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    assert not any(argv[0] == "delete" for argv in calls)
    event_file = next(runtime.extracted_dir().glob("*.json"))
    stored = json.loads(event_file.read_text(encoding="utf-8"))
    receipt = stored["candidates"][0]
    assert receipt["replacement_context_missing"] is True
    assert receipt["replacement"]["target_found"] is False


def test_unreadable_pending_files_are_quarantined(hook_env, monkeypatch, capsys):
    """Verify unreadable pending files are quarantined out of the ring."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    (runtime.pending_dir() / "broken.json").write_text("{oops", encoding="utf-8")
    cli = extractor_cli()
    events, quarantined = cli.load_pending()
    assert any("broken.json" in name for name in quarantined)
    assert (runtime.pending_dir() / "broken.json.corrupt").exists()
    assert not (runtime.pending_dir() / "broken.json").exists()
    assert len(events) == 1  # the good event is still returned


def test_repeated_failures_do_not_starve_later_events(hook_env, monkeypatch, capsys):
    """Verify repeatedly failing events do not starve later batches."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime, session="sess-1", turn="t-1")
    stage_pending(hook_env, monkeypatch, runtime, session="sess-2", turn="t-2")
    cli = extractor_cli()
    events, _quarantined = cli.load_pending()
    failing = next(event for event in events if event["event_id"] == runtime.event_id_for("sess-1", "t-1"))
    failing_path = failing["_path"]
    failing.pop("_path")
    failing.pop("_fingerprint", None)
    failing["last_error"] = "old failure"
    failing["attempts"] = 3
    runtime.write_json_private(failing_path, failing)
    for server, _calls in extraction_provider_stub(monkeypatch, []):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.extend(["--limit", "1"])
        cli.main(argv)
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["event_id"] == runtime.event_id_for("sess-2", "t-2")


def test_capture_overwrites_its_own_event_at_capacity(hook_env, monkeypatch, capsys):
    """Verify a repeated Stop overwrites its own event even at capacity."""
    runtime = load("lifecycle_runtime")
    stop = load("turn_capture")
    stage_scratch(monkeypatch, runtime)
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1", "last_assistant_message": "reply"
    })
    assert stop.main() is None
    assert len(list(runtime.pending_dir().glob("*.json"))) == 1
    monkeypatch.setattr(runtime, "pending_count", lambda: runtime.MAX_PENDING_EVENTS)
    stage_scratch(monkeypatch, runtime)
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1",
        "last_assistant_message": "updated reply",
    })
    assert stop.main() is None
    assert len(list(runtime.pending_dir().glob("*.json"))) == 1  # overwritten, not appended
    assert runtime.count_overflow_marker() == 0  # retries never count as overflow
    stored = json.loads(next(runtime.pending_dir().glob("*.json")).read_text(encoding="utf-8"))
    assert "updated reply" in stored["assistant_text"]["text"]
    capsys.readouterr()


def test_pending_ring_capacity_never_exceeds_the_cap_under_concurrency(hook_env):
    """305 concurrent claims leave exactly 300 events and 5 counted drops."""
    runtime = load("lifecycle_runtime")
    results = []
    lock = threading.Lock()

    def claim(index):
        payload = {
            "event_id": runtime.event_id_for(f"s-{index}", f"t-{index}"),
            "status": "pending",
        }
        outcome = runtime.write_pending_event(payload)
        with lock:
            results.append(outcome)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(claim, range(runtime.MAX_PENDING_EVENTS + 5)))
    assert len(list(runtime.pending_dir().glob("*.json"))) == runtime.MAX_PENDING_EVENTS
    assert runtime.count_overflow_marker() == 5
    assert results.count("full") == 5
    assert results.count("written") == runtime.MAX_PENDING_EVENTS


def test_concurrent_writes_share_no_tmp_file(hook_env):
    """Verify concurrent writes use distinct temporary files."""
    runtime = load("lifecycle_runtime")
    target = runtime.pending_dir() / "shared.json"
    barrier = threading.Barrier(4)

    def write(index):
        barrier.wait()
        runtime.write_json_private(target, {"writer": index})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(4)))
    assert json.loads(target.read_text(encoding="utf-8"))["writer"] in range(4)
    assert not list(runtime.pending_dir().glob("*.tmp"))


def test_write_json_private_retries_windows_access_denied(hook_env, monkeypatch):
    """A transient Access Denied during the atomic replace is retried."""
    runtime = load("lifecycle_runtime")
    target = runtime.pending_dir() / "retry.json"
    real_replace = runtime.os.replace
    attempts = {"count": 0}

    def flaky_replace(src, dst):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise PermissionError(13, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(runtime.time, "sleep", lambda _seconds: None)  # instant retries
    monkeypatch.setattr(runtime.os, "replace", flaky_replace)
    runtime.write_json_private(target, {"ok": True})
    assert attempts["count"] == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}

    # A permanent denial is still swallowed by quarantine (reported, not raised).
    def always_denied(src, dst):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(runtime.os, "replace", always_denied)
    ticks = iter([0.0, 0.0, 10.0])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(ticks, 10.0))
    quarantine_source = runtime.pending_dir() / "broken.json"
    quarantine_source.write_text("{oops", encoding="utf-8")
    assert runtime.quarantine_pending(quarantine_source) is None
    monkeypatch.setattr(runtime.os, "replace", real_replace)
    assert runtime.quarantine_pending(quarantine_source) == "broken.json.corrupt"


def test_exclusive_lock_serializes_and_times_out(hook_env):
    runtime = load("lifecycle_runtime")
    with runtime.exclusive_lock("admit"):
        with pytest.raises(runtime.HookError, match="admit"):
            with runtime.exclusive_lock("admit", timeout=0.05):
                pass
    with runtime.exclusive_lock("admit"):  # releasable afterwards
        pass


def test_windows_lock_byte_initialization_retries_permission_denied(
    hook_env, monkeypatch
):
    """Competing Windows hooks can initialize a shared lock without failing."""
    runtime = load("lifecycle_runtime")
    path = runtime.events_root() / "locks" / "pending.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    real_write = runtime.os.write
    attempts = {"count": 0}

    def transiently_denied(fd, value):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError(13, "Access is denied")
        return real_write(fd, value)

    monkeypatch.setattr(runtime.os, "write", transiently_denied)
    monkeypatch.setattr(runtime.time, "sleep", lambda _seconds: None)
    try:
        runtime._ensure_windows_lock_byte(
            handle, "pending", timeout=1.0, deadline=runtime.time.monotonic() + 1.0
        )
        assert attempts["count"] == 2
        assert runtime.os.fstat(handle.fileno()).st_size == 1
    finally:
        handle.close()


def test_prune_keeps_a_concurrently_restaged_scratch(hook_env, monkeypatch):
    """Verify pruning does not remove scratch restaged during the sweep."""
    runtime = load("lifecycle_runtime")
    stage_scratch(monkeypatch, runtime)
    scratch = runtime.scratch_path_for("sess-1", "t-1")
    stale_ns = int((time.time() - runtime.SCRATCH_TTL_SECONDS - 100) * 1e9)
    stale = (scratch.stat().st_ino, stale_ns)
    probes = iter([stale, (stale[0] + 1, stale_ns + 1)])
    monkeypatch.setattr(runtime, "_file_identity", lambda path: next(probes, (0, 0)))
    assert runtime.prune_stale_scratch() == 0
    assert scratch.exists()  # the fresh restage won


def test_capture_failures_emit_content_free_diagnostics(hook_env, monkeypatch, capsys):
    """Verify capture failures emit diagnostics without turn content."""
    runtime = load("lifecycle_runtime")
    stop = load("turn_capture")
    stage_scratch(monkeypatch, runtime)

    def broken_write(payload):
        raise OSError("disk full")

    monkeypatch.setattr(runtime, "write_pending_event", broken_write)
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1",
        "last_assistant_message": "secret reply content",
    })
    assert stop.main() is None
    output = capsys.readouterr().out.strip()
    assert "systemMessage" in json.loads(output)
    assert "secret reply content" not in output


def test_stage_write_failures_emit_content_free_diagnostics(hook_env, monkeypatch, capsys):
    """Verify staging write failures emit diagnostics without turn content."""
    capture = load("user_prompt_capture")
    runtime = load("lifecycle_runtime")
    monkeypatch.setattr(
        runtime, "write_json_private",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "prompt": "secret prompt content, no remember:"
    })
    assert capture.main() == 0
    output = capsys.readouterr().out.strip()
    assert "systemMessage" in json.loads(output)
    assert "secret prompt content" not in output


def test_stage_write_failure_with_remember_emits_one_response(hook_env, monkeypatch, capsys):
    """Combine staging and remember outcomes into one hook response."""
    capture = load("user_prompt_capture")
    runtime = load("lifecycle_runtime")
    monkeypatch.setattr(
        runtime,
        "write_json_private",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        runtime,
        "call_runtime",
        lambda *a, **k: (0, json.dumps({"id": "rec-1"}), ""),
    )
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "prompt": "remember: keep one fact"
    })

    assert capture.main() == 0
    output = capsys.readouterr().out.strip()
    response = json.loads(output)
    assert "could not stage" in response["systemMessage"]
    assert "saved one explicit fact" in response["systemMessage"]


def test_prompt_without_turn_id_pairs_by_session(hook_env, monkeypatch, capsys):
    """Verify prompts without a turn ID still pair through the session fallback."""
    runtime = load("lifecycle_runtime")
    capture = load("user_prompt_capture")
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "cwd": "/work", "prompt": "plain question"
    })
    assert capture.main() == 0
    session_scratch = runtime.scratch_session_path("sess-1")
    assert session_scratch.exists()
    staged = json.loads(session_scratch.read_text(encoding="utf-8"))
    assert staged["pairing"] == "session"
    # The Stop hook still pairs it, with its own deterministic event id.
    stop = load("turn_capture")
    feed_stdin(monkeypatch, {
        "session_id": "sess-1", "turn_id": "t-1",
        "last_assistant_message": "paired reply",
    })
    assert stop.main() is None
    pending = list(runtime.pending_dir().glob("*.json"))
    assert len(pending) == 1
    stored = json.loads(pending[0].read_text(encoding="utf-8"))
    assert stored["user_text"]["excerpt"] == "plain question"
    assert pending[0].name == runtime.event_id_for("sess-1", "t-1") + ".json"
    assert not session_scratch.exists()  # consumed
    capsys.readouterr()


def test_stale_snapshots_are_never_admitted(hook_env, monkeypatch, capsys):
    """Verify a redelivered snapshot is never admitted under an older fingerprint."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    calls = []

    def fake_runtime(*argv, **kwargs):
        calls.append(argv)
        if argv[0] == "search":
            return 0, json.dumps({"memories": []}), ""
        return 0, json.dumps({"id": "rec-1"}), ""

    monkeypatch.setattr(runtime, "call_runtime", fake_runtime)
    fingerprints = iter(["loaded-digest", "changed-digest"])
    monkeypatch.setattr(runtime, "file_fingerprint", lambda path: next(fingerprints, "zzz"))
    replies = [{
        "choices": [{"message": {"content": json.dumps({
            "memories": [{"text": "stale fact", "importance": 0.5}]
        })}}]
    }]
    for server, _calls in extraction_provider_stub(monkeypatch, replies):
        argv = extractor_args(monkeypatch, server.server_port)
        argv.append("--confirm")
        assert cli.main(argv) is None
    report = json.loads(capsys.readouterr().out.strip())
    assert report["events"][0]["superseded"] is True
    assert report["events"][0]["status"] == "pending"
    assert not any(argv[0] == "add" for argv in calls)  # nothing admitted
    pending_file = next(runtime.pending_dir().glob("*.json"))
    stored = json.loads(pending_file.read_text(encoding="utf-8"))
    assert stored["status"] == "pending"  # newer content left untouched
    assert "candidates" not in stored


def test_newer_pending_capture_is_not_removed_by_an_extracted_twin(hook_env, monkeypatch):
    """Verify a redelivered capture is kept when the extracted twin is not marked stale."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    pending_file = next(runtime.pending_dir().glob("*.json"))
    runtime.extracted_dir().mkdir(parents=True, exist_ok=True)
    (runtime.extracted_dir() / pending_file.name).write_text(
        pending_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    events, quarantined = cli.load_pending()
    assert len(events) == 1
    assert quarantined == []
    assert pending_file.exists()


def test_dry_run_does_not_remove_a_failed_move_leftover(hook_env, monkeypatch):
    """Verify load_pending(mutate=False) leaves the journal untouched."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    pending_file = next(runtime.pending_dir().glob("*.json"))
    runtime.extracted_dir().mkdir(parents=True, exist_ok=True)
    archived = json.loads(pending_file.read_text(encoding="utf-8"))
    archived["pending_cleanup_failed"] = True
    (runtime.extracted_dir() / pending_file.name).write_text(
        json.dumps(archived), encoding="utf-8"
    )
    events, quarantined = cli.load_pending(mutate=False)
    assert events == []
    assert quarantined == []
    assert pending_file.exists()


def test_pending_copies_with_an_extracted_twin_are_reconciled(hook_env, monkeypatch):
    """Verify a stale pending copy is removed when its extracted twin exists."""
    runtime = load("lifecycle_runtime")
    stage_pending(hook_env, monkeypatch, runtime)
    cli = extractor_cli()
    pending_file = next(runtime.pending_dir().glob("*.json"))
    runtime.extracted_dir().mkdir(parents=True, exist_ok=True)
    archived = json.loads(pending_file.read_text(encoding="utf-8"))
    archived["pending_cleanup_failed"] = True
    (runtime.extracted_dir() / pending_file.name).write_text(
        json.dumps(archived), encoding="utf-8"
    )
    events, quarantined = cli.load_pending()
    assert events == []
    assert quarantined == []
    assert not pending_file.exists()  # stale duplicate removed
    assert (runtime.extracted_dir() / pending_file.name).exists()
