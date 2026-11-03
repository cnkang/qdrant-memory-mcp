"""Opt-in real Codex client acceptance using synthetic data and isolated storage.

Subscription mode uses the operator's existing login without reading/copying it.
Cloud mode uses a dedicated CODEX_HOME and SOAK_LLM_* environment-only credentials.
The deterministic local embedding fixture isolates harness/tool behavior; it does
not certify CPU model inference. Use --cpu-cache for real offline CPU coverage.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Embeddings(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        vectors = [
            [v / 255 + 0.01 for v in hashlib.sha256(t.encode()).digest()[:3]]
            for t in body["input"]
        ]
        data = json.dumps({"embeddings": vectors}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


def command(argv, env, cwd):
    result = subprocess.run(
        argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=240
    )
    for line in result.stderr.splitlines():
        if "Qdrant Memory is not ready." in line:
            print(line, file=sys.stderr)
    if result.returncode:
        # Do not echo external service error text or credential-bearing stderr.
        diagnostic = result.stderr[-1600:]
        for name, value in env.items():
            if value and any(
                word in name.lower() for word in ("token", "key", "secret")
            ):
                diagnostic = diagnostic.replace(value, "[REDACTED]")
        raise RuntimeError(
            f"{Path(argv[0]).name} failed with exit {result.returncode}: {diagnostic}"
        )
    return result.stdout


def tool_payload(item):
    """Decode the Runtime's JSON tool result, not the model's narrative."""
    if item.get("status") != "completed" or item.get("error"):
        raise RuntimeError("Actual Codex MCP invocation failed")
    result = item.get("result") or {}
    if result.get("isError") or result.get("is_error"):
        raise RuntimeError("Actual Runtime tool returned isError")
    blocks = [
        block.get("text")
        for block in result.get("content", [])
        if block.get("type") == "text"
    ]
    if len(blocks) != 1:
        raise RuntimeError("Expected one JSON Runtime result")
    value = json.loads(blocks[0])
    if not isinstance(value, dict) or "error" in value:
        raise RuntimeError("Invalid Runtime result")
    return value


def validate_calls(calls, required_tool, expected_arguments, expected_memory=None):
    """Verify the exact server, operation arguments and returned record IDs."""
    matched = [item for item in calls if item.get("tool") == required_tool]
    if len(matched) != 1:
        raise RuntimeError("Expected exactly one requested MCP operation")
    for item in calls:
        if item.get("server") != "qdrant-memory" or item.get("tool") not in {
            required_tool,
            "qdrant_memory_search",
        }:
            raise RuntimeError("Unexpected MCP server or operation")
        value = tool_payload(item)
        if item.get("tool") == "qdrant_memory_search" and expected_memory is not None:
            memories = value.get("memories")
            if (
                not isinstance(memories, list)
                or len(
                    [
                        memory
                        for memory in memories
                        if all(memory.get(k) == v for k, v in expected_memory.items())
                    ]
                )
                != 1
            ):
                raise RuntimeError("Search did not return the expected scoped record")
    item = matched[0]
    if item.get("arguments") != expected_arguments:
        raise RuntimeError("MCP operation arguments differ from the approved operation")
    value = tool_payload(item)
    if required_tool == "qdrant_memory_search":
        identifier = expected_memory["id"]
    else:
        action = {
            "qdrant_memory_add": "ADD",
            "qdrant_memory_update": "UPDATE",
            "qdrant_memory_delete": "DELETE",
        }[required_tool]
        identifier = value.get("id")
        if (
            value.get("action") != action
            or not isinstance(identifier, str)
            or not identifier
        ):
            raise RuntimeError("Unexpected Runtime mutation result")
        if (
            required_tool != "qdrant_memory_add"
            and identifier != expected_arguments["id"]
        ):
            raise RuntimeError("Runtime mutation returned the wrong record ID")
    return {
        "tool": required_tool,
        "server": item["server"],
        "record_id": identifier,
        "actual_client_calls": 1,
        "status": "CALL_VERIFIED",
    }


def inventory(runtime, profile, env, work):
    """Read actual stored state in the fixed test scope after each model session."""
    result = json.loads(
        command(
            [
                str(runtime),
                "--home",
                str(profile),
                "list",
                "--user",
                "codex-fixture",
                "--agent",
                "codex-fixture",
                "--limit",
                "100",
            ],
            env,
            work,
        )
    )
    records = {row["point_id"]: row for row in result["memories"]}
    if result["count"]["truncated"] or len(records) != result["count"]["total"]:
        raise RuntimeError("Incomplete stored-state snapshot")
    if any(
        row.get("user_id") != "codex-fixture" or row.get("agent_id") != "codex-fixture"
        for row in records.values()
    ):
        raise RuntimeError("Stored-state scope mismatch")
    return records


def verify_transition(before, after, identifier, text, *, action):
    """Require the intended final record and unchanged neighboring views."""
    expected_ids = set(before)
    if action == "ADD":
        if identifier in before:
            raise RuntimeError("ADD reused an existing record ID")
        expected_ids.add(identifier)
    elif action == "DELETE":
        if identifier not in before:
            raise RuntimeError("DELETE target was not present")
        expected_ids.remove(identifier)
    elif action != "UPDATE" or identifier not in before:
        raise RuntimeError("Invalid update target or action")
    if set(after) != expected_ids:
        raise RuntimeError("Operation changed the wrong set of records")
    if action != "DELETE" and after[identifier].get("text") != text:
        raise RuntimeError("Target record does not contain the approved text")
    if any(after.get(key) != row for key, row in before.items() if key != identifier):
        raise RuntimeError("Operation changed another record in the same scope")


def case(
    prompt,
    required_tool,
    env,
    work,
    provider,
    *,
    expected_arguments,
    expected_memory=None,
):
    config = [
        "plugins._default.enabled=false",
        "plugins.qdrant-memory@qdrant-memory.enabled=true",
        'marketplaces.qdrant-memory.source_type="local"',
        "marketplaces.qdrant-memory.source=" + json.dumps(str(ROOT)),
        "features.memories=false",
        "memories.generate_memories=false",
        "memories.use_memories=false",
        "features.shell_tool=false",
        "features.code_mode=false",
        'web_search="disabled"',
        'approval_policy="never"',
    ]
    # Explicit authorization applies only to this disposable profile and these
    # four synthetic-data operations, never to the user's other plugin tools.
    for tool in ("search", "add", "update", "delete"):
        config.append(
            "plugins.qdrant-memory@qdrant-memory.mcp_servers.qdrant-memory.tools."
            + "qdrant_memory_"
            + tool
            + '.approval_mode="approve"'
        )
    argv = [
        "codex",
        "--no-daemon",
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--json",
        "--skip-git-repo-check",
        "-C",
        str(work),
    ]
    for item in config + provider:
        argv += ["-c", item]
    argv += [prompt]
    output = command(argv, env, work)
    events = [
        json.loads(line) for line in output.splitlines() if line.strip().startswith("{")
    ]
    calls = []
    for event in events:
        item = event.get("item", {})
        if (
            item.get("type") == "mcp_tool_call"
            and event.get("type") == "item.completed"
        ):
            calls.append(item)
    matched = [item for item in calls if required_tool == item.get("tool", "")]
    if not matched:
        types = sorted(
            {event.get("item", {}).get("type", event.get("type")) for event in events}
        )
        messages = [
            e.get("item", {}).get("text", "")
            for e in events
            if e.get("item", {}).get("type") == "agent_message"
        ]
        raise RuntimeError(
            f"Required MCP call missing: {required_tool}; observed event types: {types}; "
            + " ".join(messages)[-1200:]
        )
    return validate_calls(calls, required_tool, expected_arguments, expected_memory)


def run(args):
    work = args.workdir.expanduser().resolve()
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    profile = work / "profile"
    env = dict(os.environ)
    for name in ("QDRANT_MEMORY_CODEX_OWNER_URL", "QDRANT_MEMORY_SHARED_TOKEN"):
        env.pop(name, None)
    env.update(
        QDRANT_MEMORY_CODEX_PROFILE=str(profile),
        QDRANT_MEMORY_CODEX_EXECUTABLE=str(args.runtime.resolve()),
    )
    provider = []
    if args.mode == "cloud":
        for key in ("SOAK_LLM_BASE_URL", "SOAK_LLM_MODEL", "SOAK_LLM_API_KEY"):
            if not env.get(key):
                raise ValueError("Missing required environment name: " + key)
        if env["SOAK_LLM_BASE_URL"].rstrip("/") != "https://ollama.com/v1":
            raise ValueError(
                "Cloud acceptance is restricted to the approved Ollama endpoint"
            )
        if "gpt" in env["SOAK_LLM_MODEL"].lower():
            raise ValueError("This CI lane requires a non-GPT Ollama model")
        env["CODEX_HOME"] = str(work / "codex-home")
        provider = [
            'model_provider="soak-ollama"',
            "model=" + json.dumps(env["SOAK_LLM_MODEL"]),
            'model_providers.soak-ollama={name="Ollama Cloud",base_url="https://ollama.com/v1",wire_api="responses",env_key="SOAK_LLM_API_KEY"}',
        ]
    plugin_list = json.loads(command(["codex", "plugin", "list", "--json"], env, work))
    if any(
        p.get("pluginId") == "qdrant-memory@qdrant-memory"
        for p in plugin_list.get("installed", [])
    ):
        if args.mode == "subscription":
            raise RuntimeError(
                "Qdrant Memory is already installed in this Codex home; use a home without an existing installation for subscription acceptance"
            )
        command(["codex", "plugin", "remove", "qdrant-memory@qdrant-memory"], env, work)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Embeddings)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        command(
            ["codex", "plugin", "marketplace", "add", str(ROOT), "--json"], env, work
        )
        command(
            ["codex", "plugin", "add", "qdrant-memory@qdrant-memory", "--json"],
            env,
            work,
        )
        setup = [
            str(args.runtime.resolve()),
            "setup",
            "--profile",
            str(profile),
            "--agent-id",
            "codex-fixture",
            "--user-id",
            "codex-fixture",
        ]
        if args.cpu_cache:
            setup += [
                "--embedding-provider",
                "fastembed",
                "--model-cache-dir",
                str(args.cpu_cache.resolve()),
            ]
        else:
            setup += [
                "--embedding-provider",
                "ollama",
                "--model",
                "synthetic-fixture",
                "--dimensions",
                "3",
                "--base-url",
                f"http://127.0.0.1:{server.server_port}",
            ]
        command(setup, env, work)
        runtime = args.runtime.resolve()
        before_add = inventory(runtime, profile, env, work)
        fact = "Codex plugin acceptance preference: blue ceramic teacup."
        first = case(
            f"Call the qdrant-memory plugin's qdrant_memory_add tool once to save exactly: {fact} "
            "This is approved synthetic test data. Do not use shell or other memory tools. Report the tool result.",
            "qdrant_memory_add",
            env,
            work,
            provider,
            expected_arguments={"text": fact},
        )
        identifier = first["record_id"]
        after_add = inventory(runtime, profile, env, work)
        verify_transition(before_add, after_add, identifier, fact, action="ADD")
        expected_memory = {
            "id": identifier,
            "text": fact,
            "user_id": "codex-fixture",
            "agent_id": "codex-fixture",
        }
        second = case(
            "In the qdrant-memory plugin, call qdrant_memory_search once with query exactly: blue ceramic teacup. "
            "Do not save anything. Report the retrieved fact and ID.",
            "qdrant_memory_search",
            env,
            work,
            provider,
            expected_arguments={"query": "blue ceramic teacup"},
            expected_memory=expected_memory,
        )
        if inventory(runtime, profile, env, work) != after_add:
            raise RuntimeError("Search changed stored memories")
        # Read-only native fixtures, never the operator's actual native directory.
        native = work / "native-fixture"
        for directory, filename in (
            ("memories", "MEMORY.md"),
            ("memories_v2", "memory_summary.md"),
        ):
            path = native / directory
            path.mkdir(parents=True)
            (path / filename).write_text("# Fixture\nPrefer green notebooks.\n")
        cli = [str(args.runtime.resolve()), "--home", str(profile), "codex"]
        preview = json.loads(
            command(
                cli + ["migrate", "--codex-home", str(native), "--dry-run"], env, work
            )
        )
        assert preview["planned"] == 1 and preview["skipped"] == 1
        imported = json.loads(
            command(
                cli + ["migrate", "--codex-home", str(native), "--confirm", "--verify"],
                env,
                work,
            )
        )
        assert imported["ok"] and imported["migration"]["processed"] == 1
        output = work / "handoff"
        command(cli + ["export", "--output", str(output), "--confirm"], env, work)
        verification = json.loads(
            command(cli + ["verify", "--output", str(output)], env, work)
        )
        assert verification["ok"] and not verification["native_verified"]
        assert verification["count"] == 2
        before_update = inventory(runtime, profile, env, work)
        replacement = "Codex plugin acceptance preference: amber ceramic teacup."
        updated = case(
            f"Using only qdrant-memory, call qdrant_memory_update once for ID {identifier} "
            f"with text exactly: {replacement} "
            "This update to the synthetic test fact is approved. Do not change other records.",
            "qdrant_memory_update",
            env,
            work,
            provider,
            expected_arguments={"id": identifier, "text": replacement},
            expected_memory=expected_memory,
        )
        after_update = inventory(runtime, profile, env, work)
        verify_transition(
            before_update, after_update, identifier, replacement, action="UPDATE"
        )
        deleted = case(
            f"Using only qdrant-memory, call qdrant_memory_delete once for ID {identifier}. "
            "This deletion of the synthetic test fact "
            "is approved. Do not delete any other record.",
            "qdrant_memory_delete",
            env,
            work,
            provider,
            expected_arguments={"id": identifier},
            expected_memory={**expected_memory, "text": replacement},
        )
        after_delete = inventory(runtime, profile, env, work)
        verify_transition(after_update, after_delete, identifier, None, action="DELETE")
        command(["codex", "plugin", "remove", "qdrant-memory@qdrant-memory"], env, work)
        assert (native / "memories/MEMORY.md").is_file()
        assert (output / "handoff.json").is_file()
        verification = json.loads(
            command(cli + ["verify", "--output", str(output)], env, work)
        )
        if inventory(runtime, profile, env, work) != after_delete:
            raise RuntimeError("Uninstall changed stored memories")
        cases = [first, second, updated, deleted]
        for verified in cases:
            verified["status"] = "PASS"
        return {
            "status": "PASS",
            "harness": command(["codex", "--version"], env, work).strip(),
            "mode": args.mode,
            "embedding": "cpu" if args.cpu_cache else "synthetic-local-http",
            "cases": cases,
            "stored_state_verified": True,
            "v1_v2_fixture_import": "PASS",
            "handoff": verification,
            "uninstall_preserves_data": True,
        }
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        # This exact local candidate was installed by the test, not a pre-existing
        # unrelated plugin. Failure must not leave a dead test backend enabled.
        subprocess.run(
            ["codex", "plugin", "remove", "qdrant-memory@qdrant-memory"],
            env=env,
            cwd=work,
            capture_output=True,
            timeout=30,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["subscription", "cloud"], required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--cpu-cache", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args)))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error_type": type(exc).__name__,
                    "detail": str(exc)
                    if isinstance(exc, (RuntimeError, ValueError))
                    else "See isolated test environment",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
