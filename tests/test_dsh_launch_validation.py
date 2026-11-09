"""Exercise the actual YAML validators embedded in both launch guides."""

import os
import json
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
    lambda text: text + '\n' + text,
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


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('conflict', [False, True])
def test_mcp_server_name_conflicts(tmp_path, guide, before, conflict):
    """Reject a competing MCP server regardless of its insertion order."""
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')
    other = patch.replace('id: cnkang-qdrant-memory-mcp', 'id: another-mcp')
    if not conflict:
        other = other.replace('serverName: qdrant-memory', 'serverName: another-server')
    selected = tmp_path / 'patch.yml'
    selected.write_text(other + '\n' + patch if before else patch + '\n' + other, encoding='utf-8')
    for validator in re.findall(r'(import sys\nimport yaml\n.*?)(?=\nPY\n|\n\'@)', guide.read_text(encoding='utf-8'), re.S):
        result = subprocess.run(
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1', str(tmp_path)],
            capture_output=True, encoding='utf-8', timeout=10,
        )
        assert (result.returncode != 0) == conflict, result


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('home_kind', ['prepared', 'old', 'inline-prepared', 'inline-old', 'dynamic-old', 'duplicate'])
def test_home_selects_prepared_profile(tmp_path, guide, home_kind):
    """Accept only the prepared home, including literal and inline CLI forms."""
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')
    expected = tmp_path / 'prepared profile'
    literal = expected if home_kind.endswith('prepared') else tmp_path / 'old-profile'
    expression = "!!js process.env.QDRANT_MEMORY_DSH_PROFILE || require('node:path').join(require('node:os').homedir(), '.qdrant-memory-dsh')"
    if home_kind == 'dynamic-old':
        replacement = "!!js '/old-profile'"
    else:
        replacement = json.dumps(literal.as_posix())
    patch = patch.replace(expression, replacement)
    if home_kind.startswith('inline-'):
        patch = patch.replace('- --home\n          - ' + replacement, '- ' + json.dumps('--home=' + literal.as_posix()))
    if home_kind == 'duplicate':
        patch = patch.replace('          - mcp', '          - --home\n          - ' + json.dumps(expected.as_posix()) + '\n          - mcp')
    selected = tmp_path / 'patch.yml'
    selected.write_text(patch, encoding='utf-8')
    for validator in re.findall(r'(import sys\nimport yaml\n.*?)(?=\nPY\n|\n\'@)', guide.read_text(encoding='utf-8'), re.S):
        result = subprocess.run(
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1', str(expected)],
            capture_output=True, encoding='utf-8', timeout=10,
        )
        assert (result.returncode == 0) == home_kind.endswith('prepared'), result


if sys.platform == 'win32':
    @pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
    @pytest.mark.parametrize('version', ['0.3.1', '0.3.0'])
    def test_powershell_launch_gate(tmp_path, guide, version):
        """Exercise Windows PowerShell validation and its selected launch path."""
        profile = tmp_path / 'profile with spaces'
        profile.mkdir()
        patch = profile / 'qdrant-memory.cordis.yml'
        patch.write_text((ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8').replace(
            'qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}'), encoding='utf-8')
        launched = tmp_path / 'launched'
        stubs = '''function uvx { $global:LASTEXITCODE = 0 }
function uv {
  $Source = $input -join "`n"
  $Source | & $env:VALIDATOR_PYTHON @($args[5..($args.Length - 1)])
  $global:LASTEXITCODE = $LASTEXITCODE
}
function dsh {
  if ($args[0] -ne 'web' -or $args[1] -ne '--patch') { throw 'Unexpected DSH args' }
  [IO.File]::WriteAllText($env:LAUNCH_MARKER, [string]$args[2])
}
'''
        script = tmp_path / 'launch.ps1'
        script.write_text(stubs + re.search(r'```powershell\n(.*?)\n```', guide.read_text(encoding='utf-8'), re.S)[1], encoding='utf-8-sig')
        env = dict(os.environ, VALIDATOR_PYTHON=sys.executable,
                   QDRANT_MEMORY_DSH_PROFILE=str(profile), LAUNCH_MARKER=str(launched))
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=env, capture_output=True, timeout=30)
        assert (result.returncode == 0) == (version == '0.3.1'), result
        assert launched.exists() == (version == '0.3.1'), result
        if launched.exists():
            assert Path(launched.read_text(encoding='utf-8')) == patch
