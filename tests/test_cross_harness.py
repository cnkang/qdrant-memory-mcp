"""Keep adapter schemas, isolation, and source packaging aligned with Runtime."""

import json
from pathlib import Path

from qdrant_memory.tools import schemas

ROOT = Path(__file__).resolve().parents[1]


def test_bridge_catalogue_is_exact_runtime_schema():
    expected = [dict(name=t['name'], description=t['description'], inputSchema=t['parameters']) for t in schemas()]
    assert json.loads((ROOT / 'integrations/managed/tools.json').read_text()) == expected


def test_dsh_overlay_is_additive_and_explicit_about_credentials():
    text = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text()
    assert text.count('- insert:') == 1
    assert "name: '@deepseek-ai/dsh-mcp-client'" in text
    assert 'id: cnkang-qdrant-memory-mcp' in text
    assert '.qdrant-memory-dsh' in text
    for key in ('QDRANT_API_KEY', 'EMBEDDING_API_KEY'):
        assert f'{key}: !!js process.env.{key}' in text
    assert 'reconnect:' not in text  # Preserve the host defaults.
    assert 'permission' not in text


def test_managed_candidate_is_not_advertised_as_published():
    package = json.loads((ROOT / 'integrations/managed/package.json').read_text())
    runtime = json.loads((ROOT / 'integrations/managed/runtime.json').read_text())
    assert package['private'] is True
    assert runtime['status'] == 'source-candidate'
    assert runtime['revision'] in runtime['url']
    assert len(runtime['sha256']) == 64
