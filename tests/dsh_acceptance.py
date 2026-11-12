"""Opt-in real official DSH client test; invoke explicitly in cross-harness CI."""

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import TaggedScalar

TRUSTED_HOME_EXPRESSION = (
    "process.env.QDRANT_MEMORY_DSH_PROFILE || "
    "require('node:path').join(require('node:os').homedir(), '.qdrant-memory-dsh')"
)
MCP_SPEC = 'qdrant-memory-mcp==' + tomllib.loads(
    (Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text(encoding='utf-8'),
)['project']['version']



def _load_dsh_config(text):
    """Parse a dumped DSH config, preserving !!js tags without evaluating expressions."""
    yaml = YAML(typ='safe')
    yaml.constructor.add_constructor(
        'tag:yaml.org,2002:js',
        lambda loader, node: TaggedScalar(loader.construct_scalar(node), tag=node.tag),
    )
    return yaml.load(text)


def _find_plugin(node, plugin_id):
    """Find one composed plugin entry by its exact id."""
    if isinstance(node, dict):
        if node.get('id') == plugin_id:
            return node
        for value in node.values():
            found = _find_plugin(value, plugin_id)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_plugin(value, plugin_id)
            if found is not None:
                return found
    return None


def test_official_dsh_client(sandbox):
    profile, _, _, env, launch, cli, _ = sandbox
    env['DSH_TEST_MODULES'] = os.environ['DSH_TEST_MODULES']
    if os.environ.get('QDRANT_TEST_SKILL_ROOT'):
        env['QDRANT_TEST_SKILL_ROOT'] = os.environ['QDRANT_TEST_SKILL_ROOT']
    env['QDRANT_TEST_CHILD'] = json.dumps({'command': launch[0], 'args': [*launch[1:], '--home', str(profile), 'mcp'], 'env': env.copy()})
    env['QDRANT_TEST_PID'] = str(profile.parent / 'dsh-child.pid')
    env['QDRANT_TEST_SERVER'] = json.dumps({'command': 'node', 'args': [str(Path(__file__).with_name('dsh-reconnect-wrapper.mjs'))], 'env': env.copy()})
    result = subprocess.run(['node', str(Path(__file__).with_name('dsh-client.mjs'))], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert 'persistence passed' in result.stdout
    assert cli('doctor')['ok'] is True  # Ownership released after the final unload.


def dsh_cli(home, tmp_path):
    """Run the pinned official CLI against a disposable DSH_HOME."""
    cli = Path(os.environ['DSH_TEST_MODULES']) / '@deepseek-ai/dsh/lib/bin.js'
    assert cli.is_file()
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    env.update(DSH_HOME=str(home), HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    return ['node', str(cli)], env


def test_official_dsh_office_zip_roundtrip_and_malformed_zip64():
    """Exercise the Office dependency's parser and bound malformed ZIP64 rejection."""
    script = r'''
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join } from 'node:path';
const require = createRequire(join(process.env.DSH_TEST_MODULES, '@deepseek-ai/libreoffice-kit/package.json'));
const { zipSync, unzipSync, strToU8, strFromU8 } = require('fflate');
const archive = zipSync({
  '文档.txt': strToU8('Office ZIP roundtrip: 中文'),
  'binary.dat': new Uint8Array([0, 127, 128, 255]),
});
const restored = unzipSync(archive);
assert.equal(strFromU8(restored['文档.txt']), 'Office ZIP roundtrip: 中文');
assert.deepEqual([...restored['binary.dat']], [0, 127, 128, 255]);
const original = Buffer.from(archive);
const end = original.length - 22;
const zip64End = Buffer.alloc(56);
zip64End.writeUInt32LE(0x06064b50, 0);
zip64End.writeBigUInt64LE(44n, 4);
zip64End.writeUInt32LE(2, 32);
zip64End.writeUInt32LE(original.readUInt32LE(end + 16), 48);
const locator = Buffer.alloc(20);
locator.writeUInt32LE(0x07064b50, 0);
locator.writeBigUInt64LE(BigInt(end), 8);
const malformed = Buffer.concat([original.subarray(0, end), zip64End, locator, original.subarray(end)]);
const central = malformed.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]));
assert.ok(central >= 0);
assert.equal(malformed.readUInt16LE(central + 30), 0);
malformed.writeUInt32LE(0xffffffff, central + 20);
assert.throws(() => unzipSync(malformed));
console.log('Office ZIP roundtrip and malformed ZIP64 rejection passed');
'''
    result = subprocess.run(
        ['node', '--input-type=module', '-e', script],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert 'malformed ZIP64 rejection passed' in result.stdout


def _assert_overlay_composes(cli, overlay, env):
    """Validate parsed plugin settings and the tagged home in a real CLI dump."""
    result = subprocess.run(['node', str(cli), 'web', '--patch', str(overlay), '--dump-config'], env=env, capture_output=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('id: cnkang-qdrant-memory-mcp') == 1, result.stdout
    composed = _load_dsh_config(result.stdout)
    plugin = _find_plugin(composed, 'cnkang-qdrant-memory-mcp')
    assert plugin is not None, result.stdout
    assert plugin.get('name') == '@deepseek-ai/dsh-mcp-client', result.stdout
    assert plugin.get('enabled', True) is not False, result.stdout
    assert plugin.get('disabled', False) is False, result.stdout
    args = plugin.get('config', {}).get('args')
    assert isinstance(args, list), result.stdout
    assert plugin.get('config', {}).get('command') == 'uvx', result.stdout
    from_indexes = [index for index, value in enumerate(args) if value == '--from']
    assert from_indexes, result.stdout
    for index in from_indexes:
        assert args[index + 1] == MCP_SPEC, result.stdout
    home_indexes = [index for index, value in enumerate(args) if value == '--home']
    assert home_indexes, result.stdout
    for index in home_indexes:
        configured_home = args[index + 1]
        assert isinstance(configured_home, TaggedScalar), result.stdout
        assert str(configured_home.tag) == 'tag:yaml.org,2002:js', result.stdout
        assert ' '.join(configured_home.value.split()) == TRUSTED_HOME_EXPRESSION, result.stdout


def test_official_dsh_cli_composes_checkout_overlay(tmp_path):
    """Compose the checkout overlay offline so local regressions are exercised."""
    cli, env = dsh_cli(tmp_path / 'dsh-home', tmp_path)
    selected = tmp_path / 'selected-profile'
    selected.mkdir()
    env['QDRANT_MEMORY_DSH_PROFILE'] = str(selected)
    overlay = Path(__file__).resolve().parents[1] / 'integrations/dsh/qdrant-memory.cordis.yml'
    _assert_overlay_composes(Path(cli[1]), overlay, env)


def test_official_dsh_cli_overlay_preserves_user_patches(tmp_path):
    """The vetted overlay composes without modifying the selected profile patch.

    Live tag content stays inside the release gate: this fixture composes the
    exact reviewed overlay from the repository, so offline runs keep coverage.
    """
    cli = Path(os.environ['DSH_TEST_MODULES']) / '@deepseek-ai/dsh/lib/bin.js'
    assert cli.is_file()
    home = tmp_path / 'dsh-home'
    profile = home / 'profiles/web'
    other = home / 'profiles/other'
    profile.mkdir(parents=True)
    other.mkdir(parents=True)
    patch = profile / 'cordis.patch.yml'
    patch.write_text('[]\n', encoding='utf-8')
    sentinel = other / 'cordis.patch.yml'
    sentinel.write_text('# unrelated profile\n[]\n', encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    selected_profile = tmp_path / 'selected-profile'
    selected_profile.mkdir(parents=True)
    env.update(
        DSH_HOME=str(home),
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),
        QDRANT_MEMORY_DSH_PROFILE=str(selected_profile),
    )
    overlay = Path(__file__).resolve().parents[1] / 'integrations/dsh/qdrant-memory.cordis.yml'
    _assert_overlay_composes(cli, overlay, env)
    assert patch.read_text() == '[]\n'
    assert sentinel.read_text() == '# unrelated profile\n[]\n'


def test_official_dsh_cli_installs_the_packed_bundle(tmp_path):
    """Install on a supported DSH version or verify an incompatible update is safe."""
    root = Path(__file__).resolve().parents[1]
    node, env = dsh_cli(tmp_path / 'dsh-home', tmp_path)
    output = tmp_path / 'packed'
    output.mkdir()
    packed = subprocess.run(
        [shutil.which('python3') or shutil.which('python'), str(root / 'scripts/pack_dsh_bundle.py'), '--output-dir', str(output)],
        cwd=root, env=env, capture_output=True, text=True, timeout=120, check=True)
    report = json.loads(packed.stdout)
    tgz = Path(report['archive'])
    assert tgz.is_file()
    legacy = subprocess.run(
        [shutil.which('npm') or shutil.which('npm.cmd'), 'pack', '@cnkang/qdrant-memory-dsh-bundle@0.1.6',
         '--ignore-scripts', '--json', '--pack-destination', str(output)],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    # A failing registry pack must surface its output; check=True would hide
    # the diagnostic behind a bare exception.
    assert legacy.returncode == 0, legacy.stdout + legacy.stderr
    legacy_report = json.loads(legacy.stdout)
    legacy_report = list(legacy_report.values())[0] if isinstance(legacy_report, dict) else legacy_report[0]
    legacy_tgz = output / legacy_report['filename']
    def install(archive):
        result = subprocess.run([*node, 'plugin', '--profile', 'memory-test', 'add', str(archive)],
                                env=env, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stderr
    install(legacy_tgz)
    sentinel = tmp_path / 'dsh-home/profiles/memory-test/prepared-memory-sentinel'
    sentinel.write_text('synthetic existing profile data')
    profile = tmp_path / 'dsh-home/profiles/memory-test'
    profile_manifest = profile / 'package.json'
    profile_manifest_before = profile_manifest.read_bytes()
    config_before = subprocess.run(
        [*node, '--profile', 'memory-test', '--dump-config'],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert config_before.returncode == 0, config_before.stderr
    add = subprocess.run([*node, 'plugin', '--profile', 'memory-test', 'add', str(tgz)],
                         env=env, capture_output=True, text=True, timeout=300)
    bundle_engine = json.loads(
        (root / 'integrations/dsh/bundle/package.json').read_text(encoding='utf-8'),
    )['engines']['dsh']
    dsh_package = json.loads(
        (Path(env['DSH_TEST_MODULES']) / '@deepseek-ai/dsh/package.json').read_text(encoding='utf-8'),
    )
    dsh_version = dsh_package['version']
    exact_engine = re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', bundle_engine)
    expected_rejection = (
        env.get('DSH_EXPECT_INCOMPATIBLE_BUNDLE') == '1'
        and exact_engine is not None
        and bundle_engine != dsh_version
    )
    if expected_rejection:
        assert add.returncode != 0, 'the official CLI installed a Bundle outside its exact DSH engine pin'
        assert 'is incompatible with dsh' in add.stderr
        assert bundle_engine in add.stderr
        assert dsh_version in add.stderr
        assert profile_manifest.read_bytes() == profile_manifest_before
        config_after = subprocess.run(
            [*node, '--profile', 'memory-test', '--dump-config'],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert config_after.returncode == 0, config_after.stderr
        assert config_after.stdout == config_before.stdout
        assert sentinel.read_text() == 'synthetic existing profile data'
        return
    assert add.returncode == 0, add.stderr
    manifest = json.loads((tmp_path / 'dsh-home/profiles/memory-test/package.json').read_text(encoding='utf-8'))
    assert '@cnkang/qdrant-memory-dsh-bundle' in manifest['dsh']['profile']['bundles']
    dump = subprocess.run([*node, '--profile', 'memory-test', '--dump-config'], env=env, capture_output=True, text=True, timeout=60)
    assert dump.returncode == 0, dump.stderr
    assert '# == @cnkang/qdrant-memory-dsh-bundle' in dump.stdout
    assert 'id: cnkang-qdrant-memory-mcp' in dump.stdout
    assert "name: '@cnkang/qdrant-memory-dsh-bundle'" in dump.stdout
    assert 'mode: legacy' in dump.stdout
    assert dump.stdout.count('id: cnkang-qdrant-memory-mcp') == 1
    assert sentinel.read_text() == 'synthetic existing profile data'
    host = tmp_path / 'dsh-home/profiles/memory-test/node_modules/@cnkang/qdrant-memory-dsh-bundle/index.js'
    env['DSH_TEST_MODULES'] = os.environ['DSH_TEST_MODULES']
    checked = subprocess.run(['node', str(root / 'tests/dsh_native_e2e/bundle-config.mjs'), str(host), str(tmp_path / 'dsh-home/profiles/memory-test')],
                             env=env, capture_output=True, text=True, timeout=30)
    assert checked.returncode == 0, checked.stderr
    # Roll back the actual npm tarball in place and compose its original MCP row.
    install(legacy_tgz)
    rollback = subprocess.run([*node, '--profile', 'memory-test', '--dump-config'],
                              env=env, capture_output=True, text=True, timeout=60)
    assert rollback.returncode == 0, rollback.stderr
    assert rollback.stdout.count('id: cnkang-qdrant-memory-mcp') == 1
    assert "name: '@deepseek-ai/dsh-mcp-client'" in rollback.stdout
    assert sentinel.read_text() == 'synthetic existing profile data'
    remove = subprocess.run([*node, 'plugin', '--profile', 'memory-test', 'remove', '@cnkang/qdrant-memory-dsh-bundle'],
                            env=env, capture_output=True, text=True, timeout=300)
    assert remove.returncode == 0, remove.stderr
    manifest = json.loads((tmp_path / 'dsh-home/profiles/memory-test/package.json').read_text(encoding='utf-8'))
    assert '@cnkang/qdrant-memory-dsh-bundle' not in manifest['dsh']['profile']['bundles']
    assert sentinel.read_text() == 'synthetic existing profile data'
