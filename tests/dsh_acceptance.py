"""Opt-in real official DSH client test; invoke explicitly in cross-harness CI."""

import json
import os
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
