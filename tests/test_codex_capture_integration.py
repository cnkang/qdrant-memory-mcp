"""Real-Runtime round trip for lifecycle capture and admission (Codex only)."""

import importlib.util
import json
import sys
import sysconfig
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "integrations/codex-lifecycle/plugin/hooks"

HOOK_ENV_NAMES = (
    "QDRANT_MEMORY_CODEX_PROFILE",
    "QDRANT_MEMORY_CODEX_EXECUTABLE",
    "QDRANT_MEMORY_CODEX_PYTHON",
    "QDRANT_MEMORY_CODEX_ROOT",
    "PLUGIN_DATA",
)


@pytest.fixture(autouse=True)
def no_bytecode_cache(monkeypatch):
    """Keep hook sources pristine: loader must not write __pycache__."""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)


def load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ExtractionStub(BaseHTTPRequestHandler):
    """Deterministic extraction replies (no external service involved)."""

    replies: list = []

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = json.dumps(self.replies.pop(0)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_capture_extract_admit_search_round_trip(sandbox, tmp_path, monkeypatch):
    """A staged turn becomes one real stored record through runtime add."""
    profile, _config_path, _config, env, _launch, cli, _embeddings = sandbox
    runtime_exe = Path(sysconfig.get_path("scripts")) / (
        "qdrant-memory.exe" if sys.platform == "win32" else "qdrant-memory"
    )
    plugin_data = tmp_path / "plugin-data"
    for name in HOOK_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_PROFILE", str(profile))
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_EXECUTABLE", str(runtime_exe))
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_ROOT", str(profile.parent))
    monkeypatch.setenv("PLUGIN_DATA", str(plugin_data))

    capture = load("user_prompt_capture")
    monkeypatch.setattr(
        "sys.stdin",
        type(
            "S",
            (),
            {
                "read": staticmethod(
                    lambda: json.dumps(
                        {
                            "session_id": "real-1",
                            "turn_id": "turn-1",
                            "cwd": "/work",
                            "prompt": "What storage limits should I know about?",
                        }
                    )
                )
            },
        )(),
    )
    assert capture.main() == 0

    stop = load("turn_capture")
    monkeypatch.setattr(
        "sys.stdin",
        type(
            "S",
            (),
            {
                "read": staticmethod(
                    lambda: json.dumps(
                        {
                            "session_id": "real-1",
                            "turn_id": "turn-1",
                            "last_assistant_message": "The pending buffer holds at most 300 events.",
                        }
                    )
                )
            },
        )(),
    )
    assert stop.main() == 0

    pending = list((profile / "events/codex/pending").glob("*.json"))
    assert len(pending) == 1

    ExtractionStub.replies = [
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "memories": [
                                    {
                                        "text": "The pending memory buffer holds at most 300 events.",
                                        "category": ["codex-auto"],
                                        "importance": 0.6,
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }
    ]
    server = ThreadingHTTPServer(("127.0.0.1", 0), ExtractionStub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        extractor = load("extract_pending")
        argv = [
            "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
            "--model", "fixture-extractor",
            "--confirm",
        ]
        assert extractor.main(argv) == 0
    finally:
        server.shutdown()
        server.server_close()

    extracted = list((profile / "events/codex/extracted").glob("*.json"))
    assert len(extracted) == 1
    stored_event = json.loads(extracted[0].read_text(encoding="utf-8"))
    assert stored_event["status"] == "extracted"
    record_id = stored_event["candidates"][0]["record_id"]
    assert isinstance(record_id, str) and record_id

    # Real Runtime CLI: the admitted text is discoverable in the profile scope.
    result = cli("search", "--query", "pending memory buffer holds")
    rows = {row["id"]: row["text"] for row in result["memories"]}
    assert rows.get(record_id) == "The pending memory buffer holds at most 300 events."
    assert not list((profile / "events/codex/pending").glob("*.json"))
