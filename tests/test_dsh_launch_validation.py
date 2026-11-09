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
BASE_MCP = """- id: installed-mcp
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: qdrant-memory
"""
OTHER_MCP = BASE_MCP.replace('qdrant-memory', 'another-server')
COMPOSED_CONFIGS = {
    'clean': '[]',
    'memory': BASE_MCP,
    'unrelated': OTHER_MCP,
    'conflict': OTHER_MCP + OTHER_MCP.replace('installed-mcp', 'second-mcp'),
    'malformed': 'plugins: [',
    'dump-failure': '[]',
    'unicode-conflict': BASE_MCP.replace('qdrant-memory', '共享记忆'),
}


@pytest.fixture(autouse=True)
def composed_profile(tmp_path):
    """Supply an empty composed profile for isolated validator tests."""
    (tmp_path / 'composed.yml').write_text('[]', encoding='utf-8')


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
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1', str(tmp_path), str(tmp_path / 'composed.yml')],
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
@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
def test_invalid_active_configuration_is_rejected(tmp_path, mutation, guide):
    """Ambiguous, dynamic, missing, and unsupported launch prefixes fail closed."""
    text = guide.read_text(encoding='utf-8')
    validators = re.findall(r'(import sys\nimport yaml\n.*?)(?=\nPY\n|\n\'@)', text, re.S)
    assert len(validators) == 2
    selected = tmp_path / 'patch.yml'
    selected.write_text(mutation((ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')), encoding='utf-8')
    for validator in validators:
        result = subprocess.run(
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1', str(tmp_path), str(tmp_path / 'composed.yml')],
            capture_output=True, encoding='utf-8', timeout=10,
        )
        assert result.returncode != 0


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('version', ['0.3.1', '0.3.0'])
@pytest.mark.parametrize('base', COMPOSED_CONFIGS)
def test_shell_launch_gate(tmp_path, guide, version, base):
    """Execute the published shell flow with inert setup and launch commands."""
    profile = tmp_path / 'profile'
    profile.mkdir()
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')
    patch = patch.replace('qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}')
    patch = patch.replace('      config:', '      decoy: [--from, qdrant-memory-mcp==0.3.1]\n      config:')
    if base == 'unicode-conflict':
        patch = patch.replace('serverName: qdrant-memory', 'serverName: 共享记忆')
    (profile / 'qdrant-memory.cordis.yml').write_text(patch, encoding='utf-8')
    launched = tmp_path / 'launched'
    # Stub provisioning, while executing the real validator with CI's Python.
    # Shell functions also avoid executable-bit and shebang differences on Windows.
    stubs = '''uvx() { return 0; }
uv() { shift 5; "$VALIDATOR_PYTHON" "$@"; }
dsh() {
  if [ "$1" = web ] && [ "$2" = --dump-config ]; then
    [ "$DUMP_FAIL" = 0 ] || return 1
    printf '%s' "$COMPOSED_CONFIG"
  elif [ "$1" = web ] && [ "$2" = --patch ]; then
    printf '%s' "$3" > "$LAUNCH_MARKER"
  else
    return 1
  fi
}
'''
    env = dict(os.environ, VALIDATOR_PYTHON=Path(sys.executable).as_posix(),
               QDRANT_MEMORY_DSH_PROFILE=profile.as_posix(), LAUNCH_MARKER=launched.as_posix(),
               COMPOSED_CONFIG=COMPOSED_CONFIGS[base], DUMP_FAIL=str(int(base == 'dump-failure')))
    script = stubs + re.search(r'```sh\n(PROFILE=.*?)\n```', guide.read_text(encoding='utf-8'), re.S)[1]
    # Windows' PATH may resolve bash to the WSL launcher without a distro.
    # Use the same Git Bash installation as the Actions shell: bash steps.
    bash = (str(Path(os.environ['ProgramFiles']) / 'Git/bin/bash.exe')
            if sys.platform == 'win32' else 'bash')
    # Feed source over stdin rather than Windows' command-line quoting rules.
    result = subprocess.run([bash, '--noprofile', '--norc', '-s'], input=script,
                            env=env, capture_output=True, encoding='utf-8', timeout=30)
    allowed = version == '0.3.1' and base in ('clean', 'unrelated')
    assert launched.exists() == allowed, result
    assert (result.returncode == 0) == allowed, result
    if launched.exists():
        assert Path(launched.read_text(encoding='utf-8')) == profile / 'qdrant-memory.cordis.yml'


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('sourced', [False, True])
def test_failed_download_stops_before_validation(tmp_path, guide, sourced):
    """Download failure returns failure while the calling shell remains alive."""
    body = re.search(r'```sh\n(PROFILE=.*?)\n```', guide.read_text(encoding='utf-8'), re.S)[1]
    script = tmp_path / 'setup.sh'
    script.write_text('''uvx() { return 0; }
curl() { printf partial > "$3"; return 22; }
uv() { : > "$CHECK_MARKER"; return 1; }
dsh() { : > "$CHECK_MARKER"; return 1; }
''' + body, encoding='utf-8', newline='\n')
    marker = tmp_path / 'validated'
    survived = tmp_path / 'survived'
    profile = tmp_path / 'profile'
    env = dict(os.environ, QDRANT_MEMORY_DSH_PROFILE=profile.as_posix(),
               CHECK_MARKER=marker.as_posix(), SURVIVED=survived.as_posix(),
               SOURCE_SCRIPT=script.as_posix(), SOURCE_MODE=str(int(sourced)))
    wrapper = '''if [ "$SOURCE_MODE" = 1 ]; then
  . "$SOURCE_SCRIPT"
else
  "$BASH" "$SOURCE_SCRIPT"
fi
status=$?
: > "$SURVIVED"
exit "$status"
'''
    bash = (str(Path(os.environ['ProgramFiles']) / 'Git/bin/bash.exe')
            if sys.platform == 'win32' else 'bash')
    result = subprocess.run([bash, '--noprofile', '--norc', '-s'], input=wrapper,
                            env=env, capture_output=True, encoding='utf-8', timeout=10)
    assert result.returncode != 0, result
    assert survived.exists(), result
    assert 'Patch download failed' in result.stderr
    assert not marker.exists()
    assert not list(profile.glob('qdrant-memory.cordis.yml*'))


@pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
@pytest.mark.parametrize('before', [False, True])
@pytest.mark.parametrize('conflict', ['none', 'memory', 'additional'])
def test_mcp_server_name_conflicts(tmp_path, guide, before, conflict):
    """Reject a competing MCP server regardless of its insertion order."""
    patch = (ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8')
    other = patch.replace('id: cnkang-qdrant-memory-mcp', 'id: another-mcp')
    if conflict != 'memory':
        other = other.replace('serverName: qdrant-memory', 'serverName: another-server')
    if conflict == 'additional':
        other += '\n' + other.replace('id: another-mcp', 'id: third-mcp')
    selected = tmp_path / 'patch.yml'
    selected.write_text(other + '\n' + patch if before else patch + '\n' + other, encoding='utf-8')
    for validator in re.findall(r'(import sys\nimport yaml\n.*?)(?=\nPY\n|\n\'@)', guide.read_text(encoding='utf-8'), re.S):
        result = subprocess.run(
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1', str(tmp_path), str(tmp_path / 'composed.yml')],
            capture_output=True, encoding='utf-8', timeout=10,
        )
        assert (result.returncode != 0) == (conflict != 'none'), result


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
            [sys.executable, '-c', validator, str(selected), 'qdrant-memory-mcp==0.3.1', str(expected), str(tmp_path / 'composed.yml')],
            capture_output=True, encoding='utf-8', timeout=10,
        )
        assert (result.returncode == 0) == home_kind.endswith('prepared'), result


if sys.platform == 'win32':
    @pytest.mark.parametrize('guide', GUIDES, ids=lambda path: path.name)
    @pytest.mark.parametrize('version', ['0.3.1', '0.3.0'])
    @pytest.mark.parametrize('base', COMPOSED_CONFIGS)
    def test_powershell_launch_gate(tmp_path, guide, version, base):
        """Exercise Windows PowerShell validation and its selected launch path."""
        profile = tmp_path / 'profile with spaces'
        profile.mkdir()
        patch = profile / 'qdrant-memory.cordis.yml'
        patch.write_text((ROOT / 'integrations/dsh/qdrant-memory.cordis.yml').read_text(encoding='utf-8').replace(
            'qdrant-memory-mcp==0.3.1', f'qdrant-memory-mcp=={version}'), encoding='utf-8')
        if base == 'unicode-conflict':
            patch.write_text(patch.read_text(encoding='utf-8').replace(
                'serverName: qdrant-memory', 'serverName: 共享记忆'), encoding='utf-8')
        launched = tmp_path / 'launched'
        stubs = '''$PSNativeCommandArgumentPassing = 'Legacy'
[Console]::OutputEncoding = [Text.Encoding]::GetEncoding(1252)
function uvx { $global:LASTEXITCODE = 0 }
function uv {
  $Source = $input -join "`n"
  $Source | & $env:VALIDATOR_PYTHON @($args[5..($args.Length - 1)])
  $global:LASTEXITCODE = $LASTEXITCODE
}
function dsh {
  if ($args[0] -eq 'web' -and $args[1] -eq '--dump-config') {
    'import os,sys; sys.stdout.buffer.write(os.environ["COMPOSED_CONFIG"].encode("utf-8")); sys.exit(int(os.environ["DUMP_FAIL"]))' | & $env:VALIDATOR_PYTHON -
    $global:LASTEXITCODE = $LASTEXITCODE
    return
  }
  if ($args[0] -ne 'web' -or $args[1] -ne '--patch') { throw 'Unexpected DSH args' }
  [IO.File]::WriteAllText($env:LAUNCH_MARKER, [string]$args[2])
}
'''
        script = tmp_path / 'launch.ps1'
        script.write_text(stubs + re.search(r'```powershell\n(.*?)\n```', guide.read_text(encoding='utf-8'), re.S)[1], encoding='utf-8-sig')
        env = dict(os.environ, VALIDATOR_PYTHON=sys.executable,
                   QDRANT_MEMORY_DSH_PROFILE=str(profile), LAUNCH_MARKER=str(launched),
                   COMPOSED_CONFIG=COMPOSED_CONFIGS[base], DUMP_FAIL=str(int(base == 'dump-failure')))
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=env, capture_output=True, timeout=30)
        allowed = version == '0.3.1' and base in ('clean', 'unrelated')
        diagnostic = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        assert (result.returncode == 0) == allowed, diagnostic
        assert launched.exists() == allowed, diagnostic
        if launched.exists():
            assert Path(launched.read_text(encoding='utf-8')) == patch
