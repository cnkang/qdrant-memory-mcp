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
