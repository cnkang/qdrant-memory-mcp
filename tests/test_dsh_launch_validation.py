"""Exercise the actual YAML validators embedded in both launch guides."""

import os
import re
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
    text = guide.read_text(encoding='utf-8')
    validators = re.findall(r'(import sys\nimport yaml\n.*?)(?=\nPY\n|\n\'@)', text, re.S)
    assert len(validators) == 2
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')
    patch = patch.replace('qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}')
    if inline:
        patch = patch.replace('- --from\n          - ', '- --from=')
    patch = patch.replace('      config:', '      unrelated: [--from, qdrant-memory-mcp==0.3.1]\n      config:')
    selected = tmp_path / 'patch.yml'
    selected.write_text(patch, encoding='utf-8')
    for validator in validators:
        result = subprocess.run(
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1'],
            capture_output=True, encoding='utf-8', timeout=10,
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
    text = GUIDES[0].read_text(encoding='utf-8')
    validator = re.search(r'(import sys\nimport yaml\n.*?)\nPY\n', text, re.S)[1]
    selected = tmp_path / 'patch.yml'
    selected.write_text(mutation((ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')), encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1'],
        capture_output=True, encoding='utf-8', timeout=10,
    )
    assert result.returncode != 0


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('version', ['0.3.1', '0.3.0'])
def test_shell_launch_gate(tmp_path, guide, version):
    """Execute the published shell flow with inert setup and launch commands."""
    profile = tmp_path / 'profile'
    profile.mkdir()
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')
    patch = patch.replace('qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}')
    patch = patch.replace('      config:', '      decoy: [--from, qdrant-memory-mcp==0.3.1]\n      config:')
    (profile / 'qdrant-memory.cordis.yml').write_text(patch, encoding='utf-8')
    launched = tmp_path / 'launched'
    # Stub provisioning, while executing the real validator with CI's Python.
    # Shell functions also avoid executable-bit and shebang differences on Windows.
    stubs = '''uvx() { return 0; }
uv() { shift 5; "$VALIDATOR_PYTHON" "$@"; }
dsh() { : > "$LAUNCH_MARKER"; }
'''
    env = dict(os.environ, VALIDATOR_PYTHON=Path(sys.executable).as_posix(),
               QDRANT_MEMORY_DSH_PROFILE=profile.as_posix(), LAUNCH_MARKER=launched.as_posix())
    script = stubs + re.search(r'```sh\n(PROFILE=.*?)\n```', guide.read_text(encoding='utf-8'), re.S)[1]
    # Windows' PATH may resolve bash to the WSL launcher without a distro.
    # Use the same Git Bash installation as the Actions shell: bash steps.
    bash = (str(Path(os.environ['ProgramFiles']) / 'Git/bin/bash.exe')
            if sys.platform == 'win32' else 'bash')
    # Feed source over stdin rather than Windows' command-line quoting rules.
    result = subprocess.run([bash, '--noprofile', '--norc', '-s'], input=script,
                            env=env, capture_output=True, encoding='utf-8', timeout=30)
    assert launched.exists() == (version == '0.3.1'), result
    assert (result.returncode == 0) == (version == '0.3.1'), result
