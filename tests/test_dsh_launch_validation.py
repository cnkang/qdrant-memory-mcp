"""Exercise the actual YAML validators embedded in both launch guides."""

import re
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDES = [ROOT / 'docs' / name for name in (
    'dsh-integration.md', 'dsh-integration.zh-CN.md',
)]


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('inline', [False, True])
@pytest.mark.parametrize('version', ['0.3.1', '0.3.0', '9.9.9'])
def test_effective_args_select_prepared_package(tmp_path, guide, inline, version):
    """Only the active args prefix can authorize launching the prepared version."""
    text = guide.read_text()
    validators = re.findall(r'(import sys\nimport yaml\n.*?)(?=\nPY\n|\n\'@)', text, re.S)
    assert len(validators) == 2
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text()
    patch = patch.replace('qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}')
    if inline:
        patch = patch.replace('- --from\n          - ', '- --from=')
    patch = patch.replace('      config:', '      unrelated: [--from, qdrant-memory-mcp==0.3.1]\n      config:')
    selected = tmp_path / 'patch.yml'
    selected.write_text(patch)
    for validator in validators:
        result = subprocess.run(
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1'],
            capture_output=True, text=True, timeout=10,
        )
        assert (result.returncode == 0) == (version == '0.3.1'), result.stderr


@pytest.mark.parametrize('mutation', [
    lambda text: text.replace('- --from', '- !!js --from'),
    lambda text: text.replace('        args:', '        args: []\n        args:'),
    lambda text: text.replace('        args:', '        decoy:'),
    lambda text: text.replace('command: uvx', 'command: other'),
    lambda text: text.replace('- --from', '- --unknown'),
    lambda text: text.replace('- --from\n          - qdrant-memory-mcp==0.3.1', '- --from'),
    lambda text: text + '\n- id: cnkang-qdrant-memory-mcp\n  config:\n    args: [--from=qdrant-memory-mcp==0.3.0, qdrant-memory-mcp]\n',
])
def test_invalid_active_configuration_is_rejected(tmp_path, mutation):
    """Ambiguous, dynamic, missing, and unsupported launch prefixes fail closed."""
    text = GUIDES[0].read_text()
    validator = re.search(r'(import sys\nimport yaml\n.*?)\nPY\n', text, re.S)[1]
    selected = tmp_path / 'patch.yml'
    selected.write_text(mutation((ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text()))
    result = subprocess.run(
        [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1'],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('version', ['0.3.1', '0.3.0'])
def test_shell_launch_gate(tmp_path, guide, version):
    """Execute the published shell flow with inert setup and launch commands."""
    profile = tmp_path / 'profile'
    profile.mkdir()
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text()
    patch = patch.replace('qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}')
    patch = patch.replace('      config:', '      decoy: [--from, qdrant-memory-mcp==0.3.1]\n      config:')
    (profile / 'qdrant-memory.cordis.yml').write_text(patch)
    binary = tmp_path / 'bin'
    binary.mkdir()
    launched = tmp_path / 'launched'
    for name, body in [('uvx', 'exit 0'), ('dsh', 'touch "$LAUNCH_MARKER"')]:
        stub = binary / name
        stub.write_text('#!/bin/sh\n' + body + '\n')
        stub.chmod(0o755)
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
               QDRANT_MEMORY_DSH_PROFILE=str(profile), LAUNCH_MARKER=str(launched))
    script = re.search(r'```sh\n(PROFILE=.*?)\n```', guide.read_text(), re.S)[1]
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True,
                            text=True, timeout=30)
    assert launched.exists() == (version == '0.3.1'), result.stderr
    assert (result.returncode == 0) == (version == '0.3.1'), result.stderr
