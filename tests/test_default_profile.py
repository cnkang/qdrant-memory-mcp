"""Verify the Registry's default uvx-style package arguments use an isolated home."""

import asyncio
import json
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytest_plugins = ["test_protocol"]


def test_registry_default_profile_launch(sandbox):
    profile, _, _, env, launch, _, _ = sandbox
    default = profile.parent / ".qdrant-memory"
    profile.rename(default)
    result = subprocess.run([*launch, "status"], cwd=default.parent, env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr

    async def check():
        params = StdioServerParameters(command=launch[0], args=[*launch[1:], "mcp"], env=env, cwd=str(default.parent))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 4
                added = await session.call_tool("qdrant_memory_add", {"text": "default profile fact"})
                assert not added.isError
                memory_id = json.loads(added.content[0].text)["id"]
                deleted = await session.call_tool("qdrant_memory_delete", {"id": memory_id})
                assert not deleted.isError

    asyncio.run(check())
