"""Offline release safety checks; never create external tags or releases."""
import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / 'integrations/workbuddy/release.py'
    assert path.is_file(), 'WorkBuddy release support is missing'
    spec = importlib.util.spec_from_file_location('workbuddy_release', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def source(tmp_path):
    git(tmp_path, 'init', '-b', 'main')
    git(tmp_path, 'config', 'user.email', 'test@example.invalid')
    git(tmp_path, 'config', 'user.name', 'Test')
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion = "1.2.3"\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-m', 'initial')
    git(tmp_path, 'tag', 'v1.2.3')
    git(tmp_path, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    return tmp_path


def test_validate_existing_tag_at_clean_merged_head(source):
    release = module()
    assert release.validate_source(source, 'v1.2.3')[0] == git(source, 'rev-parse', 'HEAD')


@pytest.mark.parametrize('tag', ['1.2.3', 'v01.2.3', 'v1.2.4', 'v1.2.3-other'])
def test_invalid_or_mismatched_tag(source, tag):
    with pytest.raises(ValueError):
        module().validate_source(source, tag)


def test_dirty_tracked_tree_rejected(source):
    (source / 'pyproject.toml').write_text('[project]\nversion = "1.2.3"\n# dirty\n')
    with pytest.raises(ValueError, match='tracked'):
        module().validate_source(source, 'v1.2.3')


def test_tag_must_match_head(source):
    (source / 'other').write_text('new')
    git(source, 'add', '.')
    git(source, 'commit', '-m', 'next')
    with pytest.raises(ValueError, match='checkout'):
        module().validate_source(source, 'v1.2.3')


def test_commit_must_be_on_main(source):
    git(source, 'update-ref', '-d', 'refs/remotes/origin/main')
    with pytest.raises(ValueError, match='main'):
        module().validate_source(source, 'v1.2.3')


class API:
    def __init__(self, draft=True, immutable=False):
        self.release = {'id': 1, 'tag_name': 'v1.2.3', 'draft': draft, 'immutable': immutable}
        self.assets = []
        self.payloads = {}
        self.writes = []
        self.current_count = 0

    def verify_tag(self, tag, sha):
        pass

    def find_release(self, tag):
        return self.release

    def create_draft(self, tag, sha, notes):
        self.writes.append('create')
        self.release = {'id': 1, 'tag_name': tag, 'draft': True}
        return self.release

    def list_assets(self, release_id):
        return self.assets

    def download_asset(self, asset):
        return self.payloads[asset['id']]

    def get_release(self, release_id):
        self.current_count += 1
        return self.release

    def upload_asset(self, current, path):
        self.writes.append(path.name)
        asset = {'id': len(self.assets) + 1, 'name': path.name}
        self.assets.append(asset)
        self.payloads[asset['id']] = path.read_bytes()


@pytest.fixture
def paths(tmp_path):
    archive = tmp_path / 'test.zip'
    archive.write_bytes(b'archive')
    checksum = tmp_path / 'test.zip.sha256'
    checksum.write_text(hashlib.sha256(b'archive').hexdigest() + '  test.zip\n')
    return [archive, checksum]


def test_missing_release_created_as_draft_and_verified(paths):
    api = API()
    api.release = None
    module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert api.writes == ['create', 'test.zip', 'test.zip.sha256']
    assert api.current_count == 2


def test_all_assets_compared_before_any_upload(paths):
    api = API()
    api.assets = [{'id': 1, 'name': paths[1].name}]
    api.payloads[1] = b'wrong'
    with pytest.raises(ValueError, match='differs'):
        module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert not api.writes


@pytest.mark.parametrize('draft,immutable', [(False, False), (True, True)])
def test_missing_assets_on_published_or_immutable_release_fail(paths, draft, immutable):
    api = API(draft, immutable)
    with pytest.raises(ValueError, match='new approved'):
        module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert not api.writes


def test_completed_published_release_is_idempotent(paths):
    api = API(False, True)
    for path in paths:
        api.upload_asset(api.release, path)
    api.writes.clear()
    module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert not api.writes


def test_release_rechecked_before_each_upload(paths):
    api = API()
    upload = api.upload_asset
    def publish(current, path):
        upload(current, path)
        api.release['draft'] = False
    api.upload_asset = publish
    with pytest.raises(ValueError, match='Draft'):
        module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert api.writes == ['test.zip']


def test_request_exception_does_not_expose_body_or_token():
    import requests
    release = module()
    api = release.GitHubAPI('owner/repo', 'secret-token')
    def fail(*args, **kwargs):
        raise requests.RequestException('response body secret-token')
    api.session.request = fail
    with pytest.raises(ValueError) as error:
        api.request('GET', api.base)
    assert 'secret-token' not in str(error.value)
    assert 'response body' not in str(error.value)


@pytest.fixture
def asset_source(source):
    import json
    import zipfile
    (source / 'runtime-source.json').write_text('{"version": "0.2.2"}')
    config = source / 'integrations/workbuddy'
    config.mkdir(parents=True)
    (config / 'connector-meta.json').write_text(json.dumps({'version': '0.1.0'}))
    launcher = {'name': '@cnkang/qdrant-memory-launcher', 'version': '0.1.0-rc.1', 'integrity': 'sha512-' + 'A' * 86 + '=='}
    (source / 'launcher-source.json').write_text(json.dumps(launcher))
    mcp = {'mcpServers': {'qdrant-memory': {'type': 'stdio', 'command': 'npx', 'args': ['-y', '@cnkang/qdrant-memory-launcher@0.1.0-rc.1', 'mcp', 'workbuddy', '--auto-setup'], 'runtime': {'type': 'node', 'version': '20'}, 'npmRegistries': ['https://registry.npmjs.org', 'https://registry.npmmirror.com'], 'timeout': 30000}}}
    (config / 'mcp.json').write_text(json.dumps(mcp))
    skill = {'version': '0.2.5', 'repository': 'https://github.com/cnkang/skills.git', 'commit': 'a' * 40}
    (config / 'skill-source.json').write_text(json.dumps(skill))
    # Dependency entry is the authoritative runtime pin.
    (source / 'pyproject.toml').write_text('[project]\nversion = "1.2.3"\ndependencies = ["hermes-plugin-qdrant-memory[mcp]==0.2.2"]\n')
    directory = source / 'assets'
    directory.mkdir()
    archive = directory / 'qdrant-memory-workbuddy-connector-v0.1.0-mcp-v1.2.3.zip'
    provenance = {'connector_version': '0.1.0', 'mcp_version': '1.2.3', 'runtime_version': '0.2.2', 'launcher': launcher, 'skill_version': skill['version'], 'skill_repository': skill['repository'], 'skill_commit': skill['commit'], 'release_tag': 'v1.2.3'}
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('qdrant-memory-workbuddy/icon.svg', '<svg/>')
        output.writestr('qdrant-memory-workbuddy/skills/qdrant-memory/LICENSE', 'MIT')
        output.writestr('qdrant-memory-workbuddy/skills/qdrant-memory/SKILL.md', '# Skill')
        output.writestr('qdrant-memory-workbuddy/provenance.json', json.dumps(provenance))
        output.writestr('qdrant-memory-workbuddy/connector-meta.json', json.dumps({'version': '0.1.0'}))
        output.writestr('qdrant-memory-workbuddy/mcp.json', json.dumps(mcp))
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    return source, directory, archive, checksum


def test_validate_assets_binds_names_checksum_and_provenance(asset_source):
    root, directory, archive, checksum = asset_source
    assert module().validate_assets(root, directory, 'v1.2.3') == [archive, checksum]


@pytest.mark.parametrize('problem', ['checksum', 'extra', 'symlink', 'preview', 'provenance', 'path'])
def test_invalid_asset_directory_rejected_before_api(asset_source, problem):
    import zipfile
    root, directory, archive, checksum = asset_source
    if problem == 'checksum':
        checksum.write_text('0' * 64 + '  ' + archive.name + '\n')
    elif problem == 'extra':
        (directory / 'extra.zip').write_bytes(b'no')
    elif problem == 'symlink':
        data = archive.read_bytes()
        archive.unlink()
        other = root / 'other.zip'
        other.write_bytes(data)
        archive.symlink_to(other)
    elif problem == 'preview':
        archive.rename(archive.with_name(archive.stem + '-preview.zip'))
    else:
        with zipfile.ZipFile(archive, 'a') as output:
            if problem == 'provenance':
                with pytest.warns(UserWarning, match='Duplicate name'):
                    output.writestr('qdrant-memory-workbuddy/provenance.json', '{}')
            else:
                output.writestr('../evil', '{}')
        checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    with pytest.raises(ValueError):
        module().validate_assets(root, directory, 'v1.2.3')


def test_remote_tag_verified_before_create(paths):
    api = API()
    api.release = None
    def mismatch(tag, sha):
        raise ValueError('Remote tag mismatch')
    api.verify_tag = mismatch
    with pytest.raises(ValueError, match='Remote tag'):
        module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert not api.writes


def test_http_failure_redacts_response_body():
    release = module()
    api = release.GitHubAPI('owner/repo', 'token')
    class Response:
        ok = False
        status_code = 422
        text = 'PRIVATE RELEASE BODY'
    api.session.request = lambda *args, **kwargs: Response()
    with pytest.raises(ValueError, match='HTTP 422') as error:
        api.request('POST', api.base)
    assert 'PRIVATE' not in str(error.value)


def test_post_upload_verification_detects_corruption(paths):
    api = API()
    upload = api.upload_asset
    def corrupt(current, path):
        upload(current, path)
        api.payloads[len(api.assets)] = b'corrupt'
    api.upload_asset = corrupt
    with pytest.raises(ValueError, match='verification failed'):
        module().attach_assets(api, 'v1.2.3', 'sha', '', paths)


def test_archive_manifest_and_launch_config_must_match_inputs(asset_source):
    import json
    import zipfile
    root, directory, archive, checksum = asset_source
    with zipfile.ZipFile(archive) as original:
        files = {name: original.read(name) for name in original.namelist()}
    files['qdrant-memory-workbuddy/mcp.json'] = json.dumps({'mcpServers': {'evil': {}}}).encode()
    with zipfile.ZipFile(archive, 'w') as output:
        for name, data in files.items():
            output.writestr(name, data)
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    with pytest.raises(ValueError, match='launch'):
        module().validate_assets(root, directory, 'v1.2.3')


@pytest.mark.parametrize('annotated', [False, True])
def test_api_resolves_existing_remote_tag_without_writes(annotated):
    release = module()
    api = release.GitHubAPI('owner/repo', 'token')
    sha = 'a' * 40
    calls = []
    class Response:
        def __init__(self, obj):
            self.obj = obj
        def json(self):
            return {'object': self.obj}
    def request(method, url, **kwargs):
        calls.append((method, url))
        if annotated and '/git/ref/' in url:
            return Response({'type': 'tag', 'sha': 'b' * 40})
        return Response({'type': 'commit', 'sha': sha})
    api.request = request
    api.verify_tag('v1.2.3', sha)
    assert len(calls) == (2 if annotated else 1)
    assert all(method == 'GET' for method, url in calls)
    with pytest.raises(ValueError, match='does not match'):
        api.verify_tag('v1.2.3', 'c' * 40)


def test_duplicate_remote_assets_fail_without_mutation(paths):
    api = API()
    api.assets = [{'id': 1, 'name': paths[0].name}, {'id': 2, 'name': paths[0].name}]
    with pytest.raises(ValueError, match='Duplicate'):
        module().attach_assets(api, 'v1.2.3', 'sha', '', paths)
    assert not api.writes


def test_check_source_does_not_require_token_or_api(source, monkeypatch):
    release = module()
    release.ROOT = source
    monkeypatch.setattr('sys.argv', ['release.py', '--release-tag', 'v1.2.3', '--check-source'])
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    assert release.main() == 0


def test_runtime_provenance_must_match_runtime_source(asset_source):
    root, directory, archive, checksum = asset_source
    (root / 'runtime-source.json').write_text('{"version": "9.9.9"}')
    with pytest.raises(ValueError, match='runtime'):
        module().validate_assets(root, directory, 'v1.2.3')


def test_release_readers_are_independent_of_windows_codepage(asset_source, source, monkeypatch):
    git(source, 'add', 'pyproject.toml')
    git(source, 'commit', '-m', 'runtime dependency')
    git(source, 'tag', '-f', 'v1.2.3')
    git(source, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    read = Path.read_text
    encodings = []
    def legacy_windows_read(path, *args, **kwargs):
        encodings.append(kwargs.get('encoding'))
        kwargs.setdefault('encoding', 'cp1252')
        return read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', legacy_windows_read)
    release = module()
    release.validate_source(source, 'v1.2.3')
    root, directory, archive, checksum = asset_source
    release.validate_assets(root, directory, 'v1.2.3')
    assert encodings and all(encoding == 'utf-8' for encoding in encodings)


@pytest.mark.parametrize('required', ['icon.svg', 'skills/qdrant-memory/LICENSE', 'skills/qdrant-memory/SKILL.md'])
def test_release_archive_requires_icon_skill_and_license(asset_source, required):
    import zipfile
    root, directory, archive, checksum = asset_source
    with zipfile.ZipFile(archive) as original:
        files = {name: original.read(name) for name in original.namelist() if name != 'qdrant-memory-workbuddy/' + required}
    with zipfile.ZipFile(archive, 'w') as output:
        for name, data in files.items():
            output.writestr(name, data)
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    with pytest.raises(ValueError):
        module().validate_assets(root, directory, 'v1.2.3')


@pytest.mark.parametrize('mode,name', [(0o010644, 'fifo'), (0o020644, 'device'), (0o040755, 'directory'), (0o100644, 'empty//part'), (0o100644, 'trailing/')])
def test_archive_rejects_special_files_and_blank_path_parts(asset_source, mode, name):
    import zipfile
    root, directory, archive, checksum = asset_source
    with zipfile.ZipFile(archive, 'a') as output:
        entry = zipfile.ZipInfo('qdrant-memory-workbuddy/' + name)
        entry.create_system = 3
        entry.external_attr = mode << 16
        output.writestr(entry, b'unsafe')
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    with pytest.raises(ValueError):
        module().validate_assets(root, directory, 'v1.2.3')
