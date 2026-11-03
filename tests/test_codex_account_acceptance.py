"""Acceptance must reject successful calls that touched or returned wrong records."""

import copy
import json

import pytest
from test_release_guards import load_script


def event(tool, arguments, payload):
    return {
        "server": "qdrant-memory",
        "tool": "qdrant_memory_" + tool,
        "arguments": arguments,
        "status": "completed",
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "isError": False,
        },
    }


@pytest.mark.parametrize("missing", [False, True])
def test_case_reads_events_and_isolates_client(tmp_path, monkeypatch, missing):
    acceptance = load_script("codex_account_acceptance")
    args = {"text": "approved"}

    def cli(argv, *_):
        assert "--ignore-user-config" in argv
        assert "--ephemeral" in argv
        assert "memories.use_memories=false" in argv
        assert "features.shell_tool=false" in argv
        assert sum('.approval_mode="approve"' in value for value in argv) == 4
        item = (
            {"type": "agent_message", "text": "claimed success"}
            if missing
            else {
                "type": "mcp_tool_call",
                **event("add", args, {"id": "target", "action": "ADD"}),
            }
        )
        return "non-JSON startup message\n" + json.dumps(
            {"type": "item.completed", "item": item}
        )

    monkeypatch.setattr(acceptance, "command", cli)
    if missing:
        with pytest.raises(RuntimeError, match="Required MCP call missing"):
            acceptance.case(
                "synthetic",
                "qdrant_memory_add",
                {},
                tmp_path,
                [],
                expected_arguments=args,
            )
    else:
        assert (
            acceptance.case(
                "synthetic",
                "qdrant_memory_add",
                {},
                tmp_path,
                [],
                expected_arguments=args,
            )["record_id"]
            == "target"
        )


def test_command_redacts_external_errors(tmp_path, monkeypatch):
    from types import SimpleNamespace

    acceptance = load_script("codex_account_acceptance")
    monkeypatch.setattr(
        acceptance.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stderr="remote error synthetic-secret", stdout=""
        ),
    )
    with pytest.raises(RuntimeError) as error:
        acceptance.command(
            ["codex"], {"SOAK_LLM_API_KEY": "synthetic-secret"}, tmp_path
        )
    assert "synthetic-secret" not in str(error.value)
    assert "[REDACTED]" in str(error.value)


def test_cloud_provider_rejects_unapproved_routing(tmp_path):
    acceptance = load_script("codex_account_acceptance")
    env = {
        "SOAK_LLM_BASE_URL": "https://ollama.com/v1",
        "SOAK_LLM_MODEL": "synthetic-model",
        "SOAK_LLM_API_KEY": "synthetic-key",
    }
    provider = acceptance.cloud_provider(env, tmp_path)
    assert env["CODEX_HOME"] == str(tmp_path / "codex-home")
    assert 'model_provider="soak-ollama"' in provider
    for invalid in (
        {},
        {**env, "SOAK_LLM_BASE_URL": "https://other.invalid"},
        {**env, "SOAK_LLM_MODEL": "gpt-fixture"},
    ):
        with pytest.raises(ValueError):
            acceptance.cloud_provider(invalid, tmp_path)


@pytest.mark.parametrize("still_installed", [True, False])
def test_failed_plugin_cleanup_preserves_its_marketplace(
    tmp_path, monkeypatch, still_installed
):
    from types import SimpleNamespace

    acceptance = load_script("codex_account_acceptance")
    calls = []

    def remove(argv, **_):
        calls.append(argv)
        return SimpleNamespace(returncode=1 if "marketplace" not in argv else 0)

    installed = [{"pluginId": acceptance.PLUGIN_ID}] if still_installed else []
    monkeypatch.setattr(acceptance.subprocess, "run", remove)
    monkeypatch.setattr(
        acceptance, "command", lambda *_: json.dumps({"installed": installed})
    )
    if still_installed:
        with pytest.raises(RuntimeError, match="marketplace preserved"):
            acceptance.cleanup({}, tmp_path, True)
        assert calls == [["codex", "plugin", "remove", acceptance.PLUGIN_ID]]
    else:
        acceptance.cleanup({}, tmp_path, True)
        assert calls[-1] == ["codex", "plugin", "marketplace", "remove", "cnkang"]


def test_search_requires_expected_id_text_and_scope():
    acceptance = load_script("codex_account_acceptance")
    expected = {"id": "target", "text": "approved", "user_id": "u", "agent_id": "a"}
    args = {"query": "approved"}
    call = event("search", args, {"memories": [expected]})
    assert (
        acceptance.validate_calls([call], "qdrant_memory_search", args, expected)[
            "record_id"
        ]
        == "target"
    )
    for key in expected:
        wrong = {**expected, key: "wrong"}
        rows_to_reject = [[], [wrong], [expected, expected]]
        if key in {"user_id", "agent_id"}:
            rows_to_reject.append([expected, wrong])
        for rows in rows_to_reject:
            wrong_call = event("search", args, {"memories": rows})
            with pytest.raises(RuntimeError, match="expected scoped record"):
                acceptance.validate_calls(
                    [wrong_call],
                    "qdrant_memory_search",
                    args,
                    expected,
                )


@pytest.mark.parametrize(
    "tool,action,args",
    [
        ("add", "ADD", {"text": "approved"}),
        ("update", "UPDATE", {"id": "target", "text": "approved"}),
        ("delete", "DELETE", {"id": "target"}),
    ],
)
def test_mutation_checks_arguments_server_action_and_id(tool, action, args):
    acceptance = load_script("codex_account_acceptance")
    call = event(tool, args, {"id": "target", "action": action})
    assert (
        acceptance.validate_calls([call], "qdrant_memory_" + tool, args)["status"]
        == "CALL_VERIFIED"
    )
    bad = []
    for field, value in (
        ("server", "other"),
        ("status", "failed"),
        ("arguments", {**args, "id": "unapproved"}),
        ("tool", "prefix_qdrant_memory_" + tool),
    ):
        wrong = copy.deepcopy(call)
        wrong[field] = value
        bad.append([wrong])
    bad.append([call, call])
    bad.append(
        [
            call,
            event(
                "delete" if tool != "delete" else "update",
                {},
                {"id": "neighbor", "action": "DELETE"},
            ),
        ]
    )
    bad.append([event(tool, args, {"id": "target", "action": "SKIP"})])
    search = event("search", {"query": "approved"}, {"memories": []})
    bad.extend([[search, call], [call, search]])
    if tool != "add":
        bad.append([event(tool, args, {"id": "neighbor", "action": action})])
    for calls in bad:
        with pytest.raises(RuntimeError):
            acceptance.validate_calls(calls, "qdrant_memory_" + tool, args)


@pytest.mark.parametrize(
    "bad_result",
    [
        {"isError": True},
        {"is_error": True},
        {"content": []},
        {"content": [{"type": "text", "text": '{"error": "not performed"}'}]},
    ],
)
def test_nominally_completed_call_with_invalid_result_fails(bad_result):
    acceptance = load_script("codex_account_acceptance")
    call = event("add", {"text": "approved"}, {"id": "target", "action": "ADD"})
    call["result"] = bad_result
    with pytest.raises(RuntimeError):
        acceptance.validate_calls([call], "qdrant_memory_add", {"text": "approved"})


def test_stored_state_rejects_noop_wrong_target_and_neighbor_corruption():
    acceptance = load_script("codex_account_acceptance")
    before = {
        "target": {"text": "old", "updated_at": "old"},
        "neighbor": {"text": "control", "updated_at": "stable"},
    }
    updated = {**before, "target": {"text": "new", "updated_at": "new"}}
    acceptance.verify_transition(before, updated, "target", "new", action="UPDATE")
    deleted = {"neighbor": before["neighbor"]}
    acceptance.verify_transition(updated, deleted, "target", None, action="DELETE")
    wrong_states = [
        before,
        {"target": updated["target"]},
        {**updated, "neighbor": {"text": "corrupted"}},
        {**updated, "unexpected": {"text": "extra"}},
    ]
    for after in wrong_states:
        with pytest.raises(RuntimeError):
            acceptance.verify_transition(
                before, after, "target", "new", action="UPDATE"
            )
    for after in (
        updated,
        {},
        {"target": updated["target"]},
        {"neighbor": {"text": "corrupted"}},
    ):
        with pytest.raises(RuntimeError):
            acceptance.verify_transition(
                updated, after, "target", None, action="DELETE"
            )


def test_inventory_requires_complete_fixed_scope_snapshot(monkeypatch):
    from pathlib import Path

    acceptance = load_script("codex_account_acceptance")
    row = {
        "point_id": "id",
        "text": "approved",
        "user_id": "codex-fixture",
        "agent_id": "codex-fixture",
    }
    result = {"memories": [row], "count": {"truncated": False, "total": 1}}
    monkeypatch.setattr(acceptance, "command", lambda *_: json.dumps(result))
    assert acceptance.inventory(Path("runtime"), Path("profile"), {}, Path("work")) == {
        "id": row
    }
    for changed in (
        {**result, "count": {"truncated": True, "total": 2}},
        {**result, "count": {"truncated": False, "total": 2}},
        {**result, "memories": [{**row, "agent_id": "other"}]},
    ):
        monkeypatch.setattr(
            acceptance, "command", lambda *_, value=changed: json.dumps(value)
        )
        with pytest.raises(RuntimeError):
            acceptance.inventory(Path("runtime"), Path("profile"), {}, Path("work"))


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "update_noop",
        "update_neighbor",
        "delete_neighbor",
        "preview_counts",
        "import_counts",
        "native_text",
        "native_v2_missing",
        "native_v2_duplicate",
        "handoff_count",
        "post_uninstall_count",
        "handoff_adoption",
    ],
)
def test_run_only_passes_after_stored_state_checks(tmp_path, monkeypatch, fault):
    """Nominal tool success cannot hide a no-op or damage to another record."""
    from pathlib import Path
    from types import SimpleNamespace

    acceptance = load_script("codex_account_acceptance")
    state = {}
    verification_calls = 0
    monkeypatch.setenv("QDRANT_MEMORY_CODEX_OWNER_URL", "http://existing-owner.invalid")
    monkeypatch.setenv("QDRANT_MEMORY_SHARED_TOKEN", "synthetic-test-token")

    def row(identifier, text):
        return {
            "point_id": identifier,
            "text": text,
            "user_id": "codex-fixture",
            "agent_id": "codex-fixture",
        }

    def cli(argv, env, *_):
        nonlocal verification_calls
        assert "QDRANT_MEMORY_CODEX_OWNER_URL" not in env
        assert "QDRANT_MEMORY_SHARED_TOKEN" not in env
        if argv[0] == "codex":
            return '{"installed": []}'
        if "list" in argv:
            return json.dumps(
                {
                    "memories": list(state.values()),
                    "count": {"total": len(state), "truncated": False},
                }
            )
        if "migrate" in argv:
            if "--dry-run" in argv:
                return json.dumps(
                    {"planned": 0 if fault == "preview_counts" else 2, "skipped": 0}
                )
            state["control"] = row(
                "control",
                "wrong fixture text"
                if fault == "native_text"
                else "# Fixture\nPrefer green notebooks.",
            )
            if fault != "native_v2_missing":
                state["control_v2"] = row(
                    "control_v2",
                    "# Fixture\nPrefer green notebooks."
                    if fault == "native_v2_duplicate"
                    else "# Fixture\nPrefer amber notebooks.",
                )
            return json.dumps(
                {
                    "ok": True,
                    "migration": {"processed": 0 if fault == "import_counts" else 2},
                }
            )
        if "export" in argv:
            output = Path(argv[argv.index("--output") + 1])
            output.mkdir()
            (output / "handoff.json").write_text("{}", encoding="utf-8")
        if "verify" in argv:
            verification_calls += 1
            count = (
                1
                if fault == "handoff_count"
                or (fault == "post_uninstall_count" and verification_calls == 2)
                else 3
            )
            return json.dumps(
                {
                    "ok": True,
                    "count": count,
                    "native_verified": fault == "handoff_adoption",
                }
            )
        return "{}"

    def model(_prompt, tool, *_args, expected_arguments, **_kwargs):
        if tool == "qdrant_memory_add":
            state["target"] = row("target", expected_arguments["text"])
        elif tool == "qdrant_memory_update":
            if fault != "update_noop":
                state["target"] = row("target", expected_arguments["text"])
            if fault == "update_neighbor":
                state["control"] = row("control", "unapproved modification")
        elif tool == "qdrant_memory_delete":
            del state["control" if fault == "delete_neighbor" else "target"]
        return {"record_id": "target", "status": "CALL_VERIFIED"}

    monkeypatch.setattr(acceptance, "command", cli)
    monkeypatch.setattr(acceptance, "case", model)
    # Never invoke the production cleanup against the developer's installation.
    monkeypatch.setattr(
        acceptance.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0)
    )
    args = SimpleNamespace(
        mode="subscription",
        runtime=tmp_path / "runtime",
        workdir=tmp_path / "work",
        cpu_cache=None,
    )
    if fault:
        with pytest.raises(RuntimeError):
            acceptance.run(args)
    else:
        result = acceptance.run(args)
        assert result["status"] == "PASS"
        assert result["stored_state_verified"]
        assert all(case["status"] == "PASS" for case in result["cases"])
        assert state == {
            "control": row("control", "# Fixture\nPrefer green notebooks."),
            "control_v2": row("control_v2", "# Fixture\nPrefer amber notebooks."),
        }


@pytest.mark.parametrize(
    "failure",
    [
        "existing",
        "server",
        "setup",
        "foreign_marketplace",
        "setup_existing_marketplace",
    ],
)
def test_subscription_install_guard_and_cleanup(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace

    acceptance = load_script("codex_account_acceptance")
    calls, cleanup = [], []

    def cli(argv, *_):
        calls.append(argv)
        if argv[:3] == ["codex", "plugin", "list"]:
            installed = (
                [{"pluginId": "qdrant-memory@cnkang"}] if failure == "existing" else []
            )
            return json.dumps({"installed": installed})
        if argv[:4] == ["codex", "plugin", "marketplace", "list"]:
            entries = []
            if failure in {"foreign_marketplace", "setup_existing_marketplace"}:
                root = (
                    tmp_path / "foreign"
                    if failure == "foreign_marketplace"
                    else acceptance.ROOT
                )
                entries = [{"name": "cnkang", "root": str(root)}]
            return json.dumps({"marketplaces": entries})
        if "setup" in argv:
            raise RuntimeError("synthetic setup failure")
        return "{}"

    def broken_server(*_):
        raise RuntimeError("synthetic server failure")

    monkeypatch.setattr(acceptance, "command", cli)

    def remove(argv, **_):
        cleanup.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(acceptance.subprocess, "run", remove)
    if failure == "server":
        monkeypatch.setattr(acceptance, "ThreadingHTTPServer", broken_server)
    args = SimpleNamespace(
        mode="subscription",
        runtime=tmp_path / "runtime",
        workdir=tmp_path / "work",
        cpu_cache=None,
    )
    with pytest.raises(RuntimeError):
        acceptance.run(args)
    if failure in {"existing", "server", "foreign_marketplace"}:
        assert len(calls) == (1 if failure == "existing" else 2)
        assert cleanup == []
    else:
        assert [
            "codex",
            "plugin",
            "add",
            "qdrant-memory@cnkang",
            "--json",
        ] in calls
        expected = [["codex", "plugin", "remove", "qdrant-memory@cnkang"]]
        if failure == "setup":
            expected.append(["codex", "plugin", "marketplace", "remove", "cnkang"])
        else:
            assert not any(
                argv[:4] == ["codex", "plugin", "marketplace", "add"] for argv in calls
            )
        assert cleanup == expected
