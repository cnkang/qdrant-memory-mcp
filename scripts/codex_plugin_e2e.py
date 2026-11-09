"""Credential-free real Codex CLI end-to-end for the Qdrant Memory plugin.

Runs the actual installed Codex CLI against an isolated CODEX_HOME:

1. Repository-marketplace install with ``codex mcp`` inspection evidence.
2. Exact rebuilt ZIP install through a materialized ZIP marketplace.
3. Pinned Runtime installation into a private virtual environment from the
   plugin's own ``requirements.txt`` (never installed by the launcher).
4. Launcher ``doctor`` plus the full four-tool MCP lifecycle through the real
   Node launcher and the real Python Runtime MCP server: add, duplicate-add
   idempotency, exact-ID update, exact-ID delete, fresh-session persistence,
   hard-interruption (SIGKILL) recovery, scope isolation and post-uninstall
   data retention served by the Runtime binary directly.

Embeddings use a deterministic local HTTP fixture. No credentials are read,
created, or transmitted, and no Codex subscription is required because no model
conversation is involved. This lane complements the protected model-driven
``codex_account_acceptance.py``; it never substitutes for its evidence status.
"""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import threading
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "qdrant-memory@cnkang"
ENV_VAR_NAMES = (
    "QDRANT_MEMORY_CODEX_ROOT",
    "QDRANT_MEMORY_CODEX_PROFILE",
    "QDRANT_MEMORY_CODEX_EXECUTABLE",
    "QDRANT_MEMORY_CODEX_PYTHON",
    "QDRANT_MEMORY_CODEX_OWNER_URL",
    "QDRANT_MEMORY_SHARED_TOKEN",
    "QDRANT_API_KEY",
    "EMBEDDING_API_KEY",
)

_secret_env = {
    name: value
    for name, value in os.environ.items()
    if any(word in name.lower() for word in ("token", "key", "secret"))
}


def redact(text):
    """Strip accidental secret material from diagnostics before printing."""
    for name, value in _secret_env.items():
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def load_script(name):
    """Load a repository script module for reuse without installation."""
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package = load_script("build_codex_plugin")
acceptance = load_script("codex_account_acceptance")


def run(argv, env, cwd, *, ok=True, timeout=240):
    """Run a command and return its stdout; raise with a redacted diagnostic."""
    completed = subprocess.run(
        argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if (completed.returncode == 0) != ok:
        raise RuntimeError(
            f"{Path(argv[0]).name} exited {completed.returncode}: "
            + redact(completed.stderr[-1200:])
        )
    return completed.stdout


def codex(argv, env, workdir, *, ok=True):
    """Run the real installed Codex CLI in the isolated home."""
    return run(["codex", *argv], env, workdir, ok=ok)


class Evidence:
    """Collect executed steps with their actual outcomes."""

    def __init__(self):
        self.steps = []

    def step(self, name, **details):
        self.steps.append({"step": name, **details})
        return self.steps[-1]

    def status(self):
        """Reaching a completed report means every assert in the lane passed."""
        return 0


def bin_dir(venv):
    """Virtual environment executable directory for this host."""
    return venv / ("Scripts" if os.name == "nt" else "bin")


def launcher_env(profile, runtime_exe):
    """Host environment for the installed plugin launcher (explicit path overrides)."""
    env = {k: v for k, v in os.environ.items() if k not in _secret_env}
    for name in (
        "QDRANT_MEMORY_CODEX_ROOT",
        "QDRANT_MEMORY_CODEX_PROFILE",
        "QDRANT_MEMORY_CODEX_EXECUTABLE",
        "QDRANT_MEMORY_CODEX_PYTHON",
        "QDRANT_MEMORY_CODEX_OWNER_URL",
        "QDRANT_MEMORY_SHARED_TOKEN",
    ):
        env.pop(name, None)
    env["QDRANT_MEMORY_CODEX_PROFILE"] = str(profile)
    env["QDRANT_MEMORY_CODEX_EXECUTABLE"] = str(runtime_exe)
    return env


def install_runtime_venv(work, requirements):
    """Create the private runtime venv from the plugin's own pinned requirements."""
    venv = work / "runtime-venv"
    run(["uv", "venv", "--python", "3.11", str(venv)], os.environ, work, timeout=300)
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(bin_dir(venv) / "python"),
            "-r",
            str(requirements.resolve()),
        ],
        os.environ,
        work,
        timeout=600,
    )
    exe_name = "qdrant-memory.exe" if os.name == "nt" else "qdrant-memory"
    runtime = bin_dir(venv) / exe_name
    if not runtime.is_file():
        raise RuntimeError("Runtime console script is missing after installation")
    return venv, runtime


def assert_env_forwarding_visible(env, workdir):
    """Require every overlay env name in ``codex mcp get`` (values stay masked)."""
    server_get = codex(["mcp", "get", "qdrant-memory"], env, workdir)
    visible = [name for name in ENV_VAR_NAMES if name in server_get]
    return {
        "visible": visible,
        "all_present": set(visible) == set(ENV_VAR_NAMES),
        "server_get_tail": server_get[-1600:],
    }


def install_plugin(env, workdir, marketplace_root):
    """Install the plugin from the given marketplace and verify its package."""
    codex(
        ["plugin", "marketplace", "add", str(marketplace_root), "--json"], env, workdir
    )
    installed = json.loads(codex(["plugin", "add", PLUGIN_ID, "--json"], env, workdir))
    cache = Path(installed["installedPath"])
    assert (cache / "skills/setup/SKILL.md").is_file(), "Setup skill missing"
    assert (cache / ".codex-plugin/plugin.json").is_file(), "Codex overlay missing"
    assert (
        json.loads((cache / "plugin.json").read_text(encoding="utf-8"))["extensions"][
            "com.openai"
        ]["onboardingSkill"]
        == "./skills/setup/SKILL.md"
    ), "Onboarding skill mismatch"
    listing = json.loads(codex(["plugin", "list", "--json"], env, workdir))
    entry = next(p for p in listing["installed"] if p["pluginId"] == PLUGIN_ID)
    assert entry["enabled"], "Install reported the plugin disabled"
    env_names = assert_env_forwarding_visible(env, workdir)
    return {
        "version": installed["version"],
        "path": str(cache),
        "env_forwarding": env_names,
    }


def setup_profile_args(runtime, profile, port, user, agent):
    """Fresh isolated profile setup, matching the protected acceptance provider."""
    return [
        str(runtime),
        "setup",
        "--profile",
        str(profile),
        "--agent-id",
        agent,
        "--user-id",
        user,
        "--embedding-provider",
        "ollama",
        "--model",
        "synthetic-fixture",
        "--dimensions",
        "3",
        "--base-url",
        f"http://127.0.0.1:{port}",
    ]


def decode_tool(result):
    """Decode the Runtime's JSON tool result payload."""
    payload = result.model_dump(by_alias=True)
    assert not payload["isError"], payload
    return json.loads(payload["content"][0]["text"])


def inventory(runtime, profile, user, agent):
    """Actual stored records in the profile scope via the Runtime CLI."""
    result = json.loads(
        run(
            [
                str(runtime),
                "--home",
                str(profile),
                "list",
                "--user",
                user,
                "--agent",
                agent,
                "--limit",
                "100",
            ],
            os.environ,
            ROOT,
        )
    )
    assert not result["count"]["truncated"]
    return {row["point_id"]: row for row in result["memories"]}


@asynccontextmanager
async def launcher_mcp(launcher_path, env):
    """One MCP client session against the installed real launcher."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="node", args=[str(launcher_path), "mcp"], env=env
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            yield session


FACT_A = "Codex E2E synthetic fact: needs more espresso."
FACT_B = "Codex E2E control fact: likes round mugs."


async def four_tool_lifecycle(launcher_path, env, evidence):
    """add / duplicate-add / update / delete through the real launcher."""
    async with launcher_mcp(launcher_path, env) as session:
        tools = await session.list_tools()
        evidence.step("tools_listed", tools=sorted(t.name for t in tools.tools))
        add = decode_tool(
            await session.call_tool("qdrant_memory_add", {"text": FACT_A})
        )
        fact_a_id = add["id"]
        duplicate = decode_tool(
            await session.call_tool("qdrant_memory_add", {"text": FACT_A})
        )
        assert duplicate.get("id") == fact_a_id, "duplicate add changed the record ID"
        added_b = decode_tool(
            await session.call_tool("qdrant_memory_add", {"text": FACT_B})
        )
        fact_b_id = added_b["id"]
        updated = decode_tool(
            await session.call_tool(
                "qdrant_memory_update",
                {"id": fact_a_id, "text": "Codex E2E updated fact."},
            )
        )
        assert updated["id"] == fact_a_id, updated
        deleted = decode_tool(
            await session.call_tool("qdrant_memory_delete", {"id": fact_a_id})
        )
        assert deleted["id"] == fact_a_id, deleted
        evidence.step(
            "tools_verified",
            duplicate_add_idempotent=True,
            update=fact_a_id,
            delete=fact_a_id,
        )
    return fact_b_id


async def fresh_session_persistence(launcher_path, env, fact_b_id, evidence):
    """A new client process must still find previously stored records."""
    async with launcher_mcp(launcher_path, env) as session:
        search = decode_tool(
            await session.call_tool("qdrant_memory_search", {"query": FACT_B})
        )
        rows = {row["id"]: row["text"] for row in search["memories"]}
        assert rows.get(fact_b_id) == FACT_B, rows
    evidence.step("fresh_session_persistence", id=fact_b_id)
    return fact_b_id


def hard_kill_probe(launcher_path, env):
    """Initialize over raw stdio, then SIGKILL the launcher mid-session."""
    process = subprocess.Popen(
        ["node", str(launcher_path), "mcp"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    initialize = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "codex-e2e-interrupt", "version": "0"},
                },
            }
        )
        + "\n"
    )
    process.stdin.write(initialize.encode())
    process.stdin.flush()
    response = process.stdout.readline()
    assert response.startswith(b'{"jsonrpc"'), response[:200]
    process.send_signal(signal.SIGKILL)
    return process.wait(timeout=30)


def fetch_skills_snapshot(work):
    """Materialize the pinned cnkang/skills checkout for archive building."""
    commit = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())[
        "skill_commit"
    ]
    target = work / "skills"
    run(["git", "init", str(target)], os.environ, work)
    run(
        [
            "git",
            "-C",
            str(target),
            "remote",
            "add",
            "origin",
            "https://github.com/cnkang/skills.git",
        ],
        os.environ,
        work,
    )
    run(
        ["git", "-C", str(target), "fetch", "--depth", "1", "origin", commit],
        os.environ,
        work,
        timeout=300,
    )
    run(["git", "-C", str(target), "checkout", "FETCH_HEAD"], os.environ, work)
    return target


class FixtureHandler(BaseHTTPRequestHandler):
    """Deterministic 3-dimensional vector fixture (same contract as acceptance)."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        vectors = [
            [v / 255 + 0.01 for v in hashlib.sha256(text.encode()).digest()[:3]]
            for text in body["input"]
        ]
        payload = json.dumps({"embeddings": vectors}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


class embeddings_fixture(threading.Thread):
    """Lifecycle holder for the local HTTP fixture server."""

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        return False


def main():
    """Execute the credential-free end-to-end and print a JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--skill-repo", type=Path)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    if shutil.which("codex") is None:
        raise RuntimeError("Codex CLI is not installed on PATH")
    if shutil.which("uv") is None:
        raise RuntimeError("uv is not installed on PATH")
    if shutil.which("node") is None:
        raise RuntimeError("node is not installed on PATH")
    evidence = Evidence()
    work = args.work_dir.expanduser().resolve()
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        execute(work, evidence, args)
    finally:
        print(
            json.dumps(
                {"work": str(work), "steps": evidence.steps}, indent=2, sort_keys=True
            )
        )
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    return evidence.status()


def execute(work, evidence, args):
    """Run the whole scenario; record every executed step."""
    release = json.loads((ROOT / "plugins/qdrant-memory/release.json").read_text())
    env = {k: v for k, v in os.environ.items() if k not in _secret_env}
    for name in (
        "QDRANT_MEMORY_CODEX_ROOT",
        "QDRANT_MEMORY_CODEX_PROFILE",
        "QDRANT_MEMORY_CODEX_EXECUTABLE",
        "QDRANT_MEMORY_CODEX_PYTHON",
        "QDRANT_MEMORY_CODEX_OWNER_URL",
        "QDRANT_MEMORY_SHARED_TOKEN",
    ):
        env.pop(name, None)
    env["CODEX_HOME"] = str(work / "codex-home")
    (work / "codex-home").mkdir(mode=0o700)

    # A. Repository marketplace: install, inspect, disable-proof, remove.
    repo = install_plugin(env, work, ROOT)
    assert repo["version"] == release["plugin_version"], repo
    assert repo["env_forwarding"]["all_present"], repo["env_forwarding"]
    evidence.step(
        "repository_marketplace_install",
        version=repo["version"],
        env_forwarding_all_present=True,
    )
    codex(["plugin", "remove", PLUGIN_ID], env, work)
    codex(["plugin", "marketplace", "remove", "cnkang"], env, work)
    evidence.step("repository_marketplace_cleanup")

    # B. Exact rebuilt ZIP through a materialized ZIP marketplace.
    skills_repo = args.skill_repo or fetch_skills_snapshot(work)
    built = package.build(work / "plugin.zip", skills_repo)
    evidence.step(
        "zip_built",
        sha256=built["sha256"],
        files=built["files"],
        source_dirty=built["source_dirty"],
    )
    zip_marketplace = acceptance.prepare_zip_marketplace(
        (work / "plugin.zip").resolve(), work
    )
    zip_install = install_plugin(env, work, zip_marketplace)
    assert zip_install["version"] == release["plugin_version"], zip_install
    assert zip_install["env_forwarding"]["all_present"], zip_install["env_forwarding"]
    evidence.step("zip_marketplace_install", version=zip_install["version"])
    installed = Path(zip_install["path"])
    launcher = installed / "launcher.mjs"

    # C. Runtime venv from the installed plugin's pinned requirements.
    _, runtime = install_runtime_venv(work, installed / "requirements.txt")
    evidence.step("runtime_venv_installed", runtime=str(runtime))

    # D. Launcher doctor with an explicitly resolved private environment.
    profile = work / "profile"
    other = work / "profile-other"
    with embeddings_fixture() as fixture:
        run(
            setup_profile_args(
                runtime, profile, fixture.port, "codex-fixture", "codex-fixture"
            ),
            os.environ,
            work,
        )
        run(
            setup_profile_args(
                runtime, other, fixture.port, "codex-other", "codex-other"
            ),
            os.environ,
            work,
        )
        evidence.step("profiles_initialized", profiles=2, embedding="synthetic-fixture")

        run(["node", str(launcher), "doctor"], launcher_env(profile, runtime), work)
        evidence.step("launch_doctor", mode="doctor", exit=0)

        scoped = launcher_env(profile, runtime)
        fact_b_id = asyncio.run(four_tool_lifecycle(launcher, scoped, evidence))
        asyncio.run(fresh_session_persistence(launcher, scoped, fact_b_id, evidence))

        interrupted = hard_kill_probe(launcher, scoped)
        assert interrupted == -9 or interrupted == 137, interrupted
        asyncio.run(fresh_session_persistence(launcher, scoped, fact_b_id, evidence))
        evidence.step("sigkill_recovered", killed_exit=interrupted)

        leakage = asyncio.run(
            _other_profile_probe(launcher, launcher_env(other, runtime), fact_b_id)
        )
        assert not leakage, leakage
        evidence.step("scope_isolated", leak=0)

        before = inventory(runtime, profile, "codex-fixture", "codex-fixture")
        assert set(before) == {fact_b_id}, before

        # F. Disable, uninstall; data must survive outside the plugin.
        config = Path(env["CODEX_HOME"]) / "config.toml"
        content = config.read_text()
        config.write_text(content.replace("enabled = true", "enabled = false"))
        listing = json.loads(codex(["plugin", "list", "--json"], env, work))
        assert not next(p for p in listing["installed"] if p["pluginId"] == PLUGIN_ID)[
            "enabled"
        ], "Disable did not persist"
        evidence.step("disabled_via_config")
        codex(["plugin", "remove", PLUGIN_ID], env, work)
        assert not installed.exists(), "Uninstall retained the plugin cache"
        evidence.step("uninstalled")
        codex(["plugin", "marketplace", "remove", "cnkang"], env, work)
        after = inventory(runtime, profile, "codex-fixture", "codex-fixture")
        assert after == before, (before, after)
        # The embedding fixture stays up: the Runtime validates its embedding
        # provider at startup even for a plain re-read.
        served = asyncio.run(_runtime_direct_read(runtime, profile, fact_b_id))
        assert served == 1, served
        evidence.step("uninstall_preserved_record", served_directly=served)
        return 0


async def _other_profile_probe(launcher_path, env, fact_b_id):
    """Records from another profile must not leak into this profile's search."""
    async with launcher_mcp(launcher_path, env) as session:
        search = decode_tool(
            await session.call_tool("qdrant_memory_search", {"query": FACT_B})
        )
        return [row for row in search["memories"] if row["id"] == fact_b_id]


async def _runtime_direct_read(runtime_exe, profile, fact_b_id):
    """After removal only the Runtime binary remains; it must still serve data."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=str(runtime_exe),
        args=["--home", str(profile), "mcp"],
        env={k: v for k, v in os.environ.items() if k not in _secret_env},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = decode_tool(
                await session.call_tool("qdrant_memory_search", {"query": FACT_B})
            )
            return len([r for r in result["memories"] if r["id"] == fact_b_id])


if __name__ == "__main__":
    raise SystemExit(main())
