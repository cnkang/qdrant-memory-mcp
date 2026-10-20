"""Opt-in real official DSH client test; invoke explicitly in cross-harness CI."""

import json
import os
import shutil
import subprocess
from pathlib import Path

pytest_plugins = ['test_protocol']


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


def test_official_dsh_cli_overlay_preserves_user_patches(tmp_path):
    root = Path(__file__).resolve().parents[1]
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
    env.update(DSH_HOME=str(home), HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    result = subprocess.run(['node', str(cli), 'web', '--patch', str(root / 'integrations/dsh/qdrant-memory.cordis.yml'), '--dump-config'], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('id: cnkang-qdrant-memory-mcp') == 1
    assert "name: '@deepseek-ai/dsh-mcp-client'" in result.stdout
    assert patch.read_text() == '[]\n'
    assert sentinel.read_text() == '# unrelated profile\n[]\n'


def test_official_dsh_cli_installs_the_packed_bundle(tmp_path):
    """Real pnpm install of the packed Bundle; the layer composes and removes cleanly."""
    root = Path(__file__).resolve().parents[1]
    node, env = dsh_cli(tmp_path / 'dsh-home', tmp_path)
    npm = shutil.which('npm') or shutil.which('npm.cmd')
    assert npm, 'npm is required to pack the bundle'
    output = tmp_path / 'packed'
    output.mkdir()
    packed = subprocess.run(
        [npm, 'pack', '--json', '--ignore-scripts', '--pack-destination', str(output)],
        cwd=root / 'integrations/dsh/bundle', env=env, capture_output=True, text=True, timeout=120, check=True)
    report = json.loads(packed.stdout)
    report = list(report.values())[0] if isinstance(report, dict) else report[0]
    tgz = output / report['filename']
    assert tgz.is_file()
    add = subprocess.run([*node, 'plugin', '--profile', 'memory-test', 'add', str(tgz)],
                         env=env, capture_output=True, text=True, timeout=300)
    assert add.returncode == 0, add.stderr
    manifest = json.loads((tmp_path / 'dsh-home/profiles/memory-test/package.json').read_text(encoding='utf-8'))
    assert '@cnkang/qdrant-memory-dsh-bundle' in manifest['dsh']['profile']['bundles']
    dump = subprocess.run([*node, '--profile', 'memory-test', '--dump-config'], env=env, capture_output=True, text=True, timeout=60)
    assert dump.returncode == 0, dump.stderr
    assert '# == @cnkang/qdrant-memory-dsh-bundle' in dump.stdout
    assert 'id: cnkang-qdrant-memory-mcp' in dump.stdout
    assert "name: '@deepseek-ai/dsh-mcp-client'" in dump.stdout
    assert 'command: npx' in dump.stdout
    remove = subprocess.run([*node, 'plugin', '--profile', 'memory-test', 'remove', '@cnkang/qdrant-memory-dsh-bundle'],
                            env=env, capture_output=True, text=True, timeout=300)
    assert remove.returncode == 0, remove.stderr
    manifest = json.loads((tmp_path / 'dsh-home/profiles/memory-test/package.json').read_text(encoding='utf-8'))
    assert '@cnkang/qdrant-memory-dsh-bundle' not in manifest['dsh']['profile']['bundles']
