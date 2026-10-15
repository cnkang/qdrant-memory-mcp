"""Verify transparent warm behavior through the actual Node readiness boundary."""

import asyncio
import json
import shutil
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_protocol import test_stdout_is_jsonrpc_only as exercise_stdout

pytest_plugins = ['test_protocol']


def managed(sandbox):
    profile, path, config, env, launch, cli, embeddings = sandbox
    node = shutil.which('node')
    assert node, 'Managed bridge acceptance requires Node.js 20+'
    env['QDRANT_TEST_BACKEND'] = json.dumps({'command': launch[0], 'args': [*launch[1:], '--home', str(profile), 'mcp'], 'env': env.copy()})
    return profile, path, config, env, [node, str(Path(__file__).with_name('managed-backend.mjs'))], cli, embeddings


def test_bridge_crud_restart_scope_writerlease_and_redaction(sandbox):
    profile, _, _, env, launch, cli, _ = managed(sandbox)

    async def phase(callback):
        params = StdioServerParameters(command=launch[0], args=launch[1:], env=env)
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await asyncio.wait_for(session.initialize(), 5)
                assert len((await session.list_tools()).tools) == 4
                # Readiness polling is read-only. Never retry/queue a write.
                for _ in range(100):
                    result = await session.call_tool('qdrant_memory_search', {'query': 'readiness'})
                    if not result.isError:
                        break
                    assert 'Preparing' in result.content[0].text
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError('Runtime did not become ready')
                return await callback(session)

    async def call(session, name, arguments, ok=True):
        result = await session.call_tool('qdrant_memory_' + name, arguments)
        assert result.isError is not ok
        return json.loads(result.content[0].text)

    async def first(session):
        added = await call(session, 'add', {'text': 'managed synthetic preference'})
        memory_id = added['id']
        await call(session, 'update', {'id': memory_id, 'text': 'managed updated preference'})
        await call(session, 'add', {'text': 'denied', 'user_id': 'other'}, ok=False)
        assert cli('add', '--text', 'busy', ok=False)['error']['type'] == 'WriterBusyError'
        return memory_id

    memory_id = asyncio.run(phase(first))

    async def second(session):
        found = await call(session, 'search', {'query': 'managed updated preference'})
        assert any(m['id'] == memory_id and m['text'] == 'managed updated preference' for m in found['memories'])
        await call(session, 'delete', {'id': memory_id})

    asyncio.run(phase(second))

    async def third(session):
        found = await call(session, 'search', {'query': 'managed updated preference'})
        assert not found['memories']

    asyncio.run(phase(third))
    assert cli('doctor')['ok'] is True


def test_bridge_stdout_protocol_only(sandbox):
    exercise_stdout(managed(sandbox))
