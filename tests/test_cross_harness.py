"""Keep adapter schemas, isolation, and source packaging aligned with Runtime."""

import json
from pathlib import Path

from ruamel.yaml import YAML

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


def test_dsh_native_bundle_pins_release_and_keeps_automation_disabled():
    package_path = ROOT / 'integrations/dsh/native/package.json'
    package = json.loads(package_path.read_text())
    patch = YAML(typ='safe').load(
        (ROOT / 'integrations/dsh/native/cordis.patch.yml').read_text()
    )
    row = patch[0]['insert'][0]
    assert package['name'] == '@cnkang/qdrant-memory-dsh-native'
    assert package['private'] is True
    assert package['engines']['node'] == '>=24.9.0'
    assert package['scripts']['validate:node'] == 'node ./scripts/validate-node.mjs'
    assert package['scripts']['validate:dsh'] == 'node ./scripts/validate-dsh.mjs'
    assert package['scripts']['validate:pnpm'] == 'node ./scripts/validate-pnpm.mjs'
    assert package['scripts']['validate:host'] == (
        'npm run validate:host:add && npm run validate:host:config && npm run validate:host:remove'
    )
    assert package['dependencies'] == {
        '@deepseek-ai/cordis': '4.1.0',
        '@deepseek-ai/dsh-llm': '0.2.2-rc.1',
        '@deepseek-ai/schemastery': '3.19.0',
    }
    assert package['devDependencies']['@deepseek-ai/dsh'] == '0.2.2-rc.1'
    assert row['name'] == package['name']
    assert row['config']['auto_recall']['enabled'] is False
    assert row['config']['auto_capture']['enabled'] is False
    assert row['config']['memory_injection']['enabled'] is False
    assert 'qdrant-memory/extraction-v1' in (ROOT / 'integrations/dsh/native/index.js').read_text()

    workflow = YAML(typ='safe').load((ROOT / '.github/workflows/dsh-native.yml').read_text())
    runners = {
        (item['os'], item['arch'])
        for item in workflow['jobs']['native-contract']['strategy']['matrix']['include']
    }
    assert runners == {
        ('ubuntu-24.04', 'x64'),
        ('macos-15', 'arm64'),
        ('windows-2025', 'x64'),
    }
    workflow_text = (ROOT / '.github/workflows/dsh-native.yml').read_text()
    assert "node-version: '24.9.0'" in workflow_text
    package_manager = next(
        step for step in workflow['jobs']['native-contract']['steps']
        if step.get('name') == 'Install the exact DSH Plugin Manager package manager'
    )
    assert package_manager['uses'] == 'pnpm/action-setup@b906affcce14559ad1aafd4ab0e942779e9f58b1'
    assert package_manager['with']['version'] == '11.28.5'
    assert package_manager['with']['run_install'] is False
    assert 'validate:host' in workflow_text
    pack_step = next(
        step for step in workflow['jobs']['native-contract']['steps']
        if step.get('name') == 'Check publishable bundle contents without publishing'
    )
    assert pack_step['run'] == 'npm pack --dry-run --json'
    assert pack_step['working-directory'] == 'integrations/dsh/native'


def test_managed_launcher_uses_a_published_runtime_wheel():
    package = json.loads((ROOT / 'integrations/managed/package.json').read_text())
    runtime = json.loads((ROOT / 'integrations/managed/runtime.json').read_text())
    assert package['private'] is False
    assert runtime['status'] == 'released-wheel'
    assert runtime['url'].startswith('https://files.pythonhosted.org/')
    assert runtime['url'].endswith(f"hermes_plugin_qdrant_memory-{runtime['version']}-py3-none-any.whl")
    assert len(runtime['sha256']) == 64
