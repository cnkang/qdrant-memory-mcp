"""Keep adapter schemas, isolation, and source packaging aligned with Runtime."""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from qdrant_memory.tools import schemas

ROOT = Path(__file__).resolve().parents[1]


def test_bridge_catalogue_is_exact_runtime_schema():
    """The managed bridge catalogue exactly mirrors the Runtime schemas."""
    expected = [dict(name=t['name'], description=t['description'], inputSchema=t['parameters']) for t in schemas()]
    assert json.loads((ROOT / 'integrations/managed/tools.json').read_text()) == expected


def test_dsh_overlay_is_additive_and_explicit_about_credentials():
    """The DSH overlay adds one plugin without changing host permission defaults."""
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
    """The native bundle keeps exact pins and all automation switches off."""
    package_path = ROOT / 'integrations/dsh/native/package.json'
    package = json.loads(package_path.read_text())
    patch = YAML(typ='safe').load(
        (ROOT / 'integrations/dsh/native/cordis.patch.yml').read_text()
    )
    row = patch[0]['insert'][0]
    assert package['name'] == '@cnkang/qdrant-memory-dsh-native'
    assert package['private'] is True
    assert package['engines']['node'] == '>=24.9.0'
    assert package['scripts']['pretest'] == 'npm run validate:node'
    assert package['scripts']['validate:node'] == 'node ./scripts/validate-node.mjs'
    assert package['scripts']['validate:dsh'] == 'node ./scripts/validate-dsh.mjs'
    assert 'validate:pnpm' not in package['scripts']
    assert package['scripts']['validate:host'] == 'node ./scripts/validate-host.mjs'
    assert not any(key.startswith('validate:host:') for key in package['scripts'])
    assert package['dependencies'] == {
        '@deepseek-ai/dsh-llm': '0.2.2-rc.1',
        '@deepseek-ai/schemastery': '3.19.0',
    }
    assert package['peerDependencies'] == {'@deepseek-ai/dsh-session': '0.2.2-rc.1'}
    assert package['peerDependenciesMeta']['@deepseek-ai/dsh-session']['optional'] is True
    assert '@deepseek-ai/dsh' not in package.get('dependencies', {})
    assert '@deepseek-ai/dsh' not in package.get('devDependencies', {})
    ci_package = json.loads(
        (ROOT / '.github/ci-deps/dsh-native/package.json').read_text()
    )
    assert ci_package['private'] is True
    assert ci_package['dependencies'] == {'@deepseek-ai/dsh': '0.2.2-rc.1'}
    assert ci_package['overrides'] == {
        '@deepseek-ai/libreoffice-kit': {'fflate': '0.8.3'},
        '@modelcontextprotocol/client': '2.3.0',
        'undici': '8.12.3',
        'zod': '4.6.7',
    }
    assert (ROOT / '.nvmrc').read_text().strip() == '24'
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
    node_versions = {
        item.get('node')
        for item in workflow['jobs']['native-contract']['strategy']['matrix']['include']
    }
    assert node_versions == {'24', '24.9.0'}
    workflow_text = (ROOT / '.github/workflows/dsh-native.yml').read_text()
    assert 'node-version: ${{ matrix.node }}' in workflow_text
    quality_workflow_text = (ROOT / '.github/workflows/quality.yml').read_text()
    assert "node-version: '24'" in quality_workflow_text
    package_manager = next(
        step for step in workflow['jobs']['native-contract']['steps']
        if step.get('name') == 'Install the exact DSH Plugin Manager package manager'
    )
    assert package_manager['uses'] == 'pnpm/action-setup@b906affcce14559ad1aafd4ab0e942779e9f58b1'
    assert package_manager['with']['version'] == '11.28.5'
    assert package_manager['with']['run_install'] is False
    assert 'validate:host' in workflow_text
    assert 'validate:pnpm' not in workflow_text
    pack_step = next(
        step for step in workflow['jobs']['native-contract']['steps']
        if step.get('name') == 'Check publishable bundle contents without publishing'
    )
    assert pack_step['run'] == 'npm pack --dry-run --json'
    assert pack_step['working-directory'] == 'integrations/dsh/native'


@pytest.mark.parametrize('add,dump,remove,rm_failures,expected', [
    (0, 0, 0, 0, 0), (7, 0, 0, 0, 7), (0, 9, 0, 0, 1),
    (0, 0, 11, 0, 11), (0, 0, 0, 1, 0), (0, 0, 0, 3, 1),
    (7, 0, 0, 3, 7), (0, 0, 11, 3, 11),
])
def test_native_host_cleanup_behavior(tmp_path, add, dump, remove, rm_failures, expected):
    """Run the real host validator against fake DSH and injected cleanup failures."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable, so the host validator cannot run', allow_module_level=False)
    binary = tmp_path / 'bin'
    binary.mkdir()
    log = tmp_path / 'actions.jsonl'
    fake = binary / 'fake-dsh.mjs'
    fake.write_text('''import { appendFileSync, mkdirSync, rmSync, existsSync } from 'node:fs'
import { join } from 'node:path'
const args = process.argv.slice(2)
const home = process.env.DSH_HOME
const profile = join(home, 'profiles/qdrant-native-ci')
const event = { args, home }
let status = 0
if (args.includes('add')) {
  mkdirSync(profile, { recursive: true })
  status = Number(process.env.FAKE_ADD)
} else if (args.includes('remove')) {
  event.profileExisted = existsSync(profile)
  rmSync(profile, { recursive: true, force: true })
  event.profileRemoved = !existsSync(profile)
  status = Number(process.env.FAKE_REMOVE)
} else if (args.includes('--dump-config')) {
  console.log(`- id: qdrant-memory-native
  config:
    auto_recall:
      enabled: false
    auto_capture:
      enabled: false
    memory_injection:
      enabled: false`)
  status = Number(process.env.FAKE_DUMP)
} else { status = 99 }
appendFileSync(process.env.FAKE_LOG, JSON.stringify(event) + '\\n')
process.exit(status)
''', encoding='utf-8')
    if os.name == 'nt':
        (binary / 'dsh.cmd').write_text(f'@"{node}" "{fake}" %*\n', encoding='utf-8')
    else:
        command = binary / 'dsh'
        # A shell launcher quotes the interpreter, so a Node path containing
        # spaces cannot split into two arguments before the fake runs.
        launcher = f'#!/bin/sh\nexec {shlex.quote(node)} {shlex.quote(str(fake))} "$@"\n'
        command.write_text(launcher, encoding='utf-8')
        command.chmod(0o755)
    preload = tmp_path / 'cleanup.mjs'
    preload.write_text('''import fs from 'node:fs'
import { basename } from 'node:path'
import { syncBuiltinESMExports } from 'node:module'
const original = fs.rmSync
let attempts = 0
fs.rmSync = (path, options) => {
  if (basename(String(path)).startsWith('dsh-native-ci-')) {
    attempts += 1
    fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify({ cleanup: attempts }) + '\\n')
    if (attempts <= Number(process.env.FAKE_RM_FAILURES)) {
      throw Object.assign(new Error('injected busy directory'), { code: 'EBUSY' })
    }
  }
  return original(path, options)
}
syncBuiltinESMExports()
''', encoding='utf-8')
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
               FAKE_ADD=str(add), FAKE_DUMP=str(dump), FAKE_REMOVE=str(remove),
               FAKE_RM_FAILURES=str(rm_failures), FAKE_LOG=str(log),
               NODE_OPTIONS=f'--import={preload.as_uri()}')
    result = subprocess.run([node, './scripts/validate-host.mjs'],
                            cwd=ROOT / 'integrations/dsh/native', env=env,
                            capture_output=True, encoding='utf-8', timeout=20)
    actions = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    home = Path(next(item['home'] for item in actions if 'home' in item))
    try:
        assert result.returncode == expected, result
        removal = next(item for item in actions if 'remove' in item.get('args', []))
        assert removal['profileExisted'], removal
        assert removal['profileRemoved'], removal
        assert home.exists() == (rm_failures == 3)
        assert len([item for item in actions if 'cleanup' in item]) == min(rm_failures + 1, 3)
        assert ('cleanup failed: EBUSY' in result.stderr) == (rm_failures == 3)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_sonar_classifies_dsh_fixtures_and_validators_as_tests():
    """Sonar keeps fixtures and validators out of production coverage."""
    properties = {
        key: value
        for line in (ROOT / 'sonar-project.properties').read_text().splitlines()
        if line and not line.startswith('#')
        for key, value in [line.split('=', 1)]
    }
    assert properties['sonar.tests'] == (
        'tests,integrations/dsh/native/test,integrations/dsh/native/scripts'
    )
    assert properties['sonar.exclusions'] == (
        'integrations/dsh/native/test/**,integrations/dsh/native/scripts/**,'
        'integrations/dsh/bundle/native/**'
    )


def test_managed_launcher_uses_a_published_runtime_wheel():
    """The managed launcher resolves a published Runtime wheel, never a checkout."""
    package = json.loads((ROOT / 'integrations/managed/package.json').read_text())
    runtime = json.loads((ROOT / 'integrations/managed/runtime.json').read_text())
    assert package['private'] is False
    assert runtime['status'] == 'released-wheel'
    assert runtime['url'].startswith('https://files.pythonhosted.org/')
    assert runtime['url'].endswith(f"hermes_plugin_qdrant_memory-{runtime['version']}-py3-none-any.whl")
    assert len(runtime['sha256']) == 64
