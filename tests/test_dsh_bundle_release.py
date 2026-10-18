"""Offline DSH bundle release safety checks; never create external tags or releases."""

import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / 'scripts/dsh_bundle_release.py'
    assert path.is_file(), 'DSH bundle release support is missing'
    spec = importlib.util.spec_from_file_location('dsh_bundle_release', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def bundle_version(root):
    """Read the declared version so a bump never needs a test edit."""
    meta = json.loads((root / 'integrations/dsh/bundle/package.json').read_text(encoding='utf-8'))
    return meta['version']


@pytest.fixture
def release_tag(source):
    return 'dsh-bundle-v' + bundle_version(source)


@pytest.fixture
def source(tmp_path):
    git(tmp_path, 'init', '-b', 'main')
    git(tmp_path, 'config', 'user.email', 'test@example.invalid')
    git(tmp_path, 'config', 'user.name', 'Test')
    shutil.copytree(ROOT / 'integrations/dsh/bundle', tmp_path / 'integrations/dsh/bundle')
    (tmp_path / 'scripts').mkdir()
    shutil.copy(ROOT / 'scripts/pack_dsh_bundle.py', tmp_path / 'scripts/pack_dsh_bundle.py')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-m', 'initial')
    git(tmp_path, 'tag', 'dsh-bundle-v' + bundle_version(tmp_path))
    git(tmp_path, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    return tmp_path


def craft_archive(directory, bundle):
    archive = directory / ('cnkang-qdrant-memory-dsh-bundle-' + json.loads((bundle / 'package.json').read_text(encoding='utf-8'))['version'] + '.tgz')
    with tarfile.open(archive, 'w:gz') as output:
        for name in sorted(['package.json', 'cordis.patch.yml', 'README.md', 'LICENSE']):
            data = (bundle / name).read_bytes()
            member = tarfile.TarInfo('package/' + name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    checksum = directory / (archive.name + '.sha256')
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    return archive, checksum


@pytest.fixture
def assets(tmp_path, source):
    directory = tmp_path / 'assets'
    directory.mkdir()
    return (source, *craft_archive(directory, source / 'integrations/dsh/bundle'))


def test_validate_existing_tag_at_clean_merged_head(source, release_tag):
    assert module().validate_source(source, release_tag)[0] == git(source, 'rev-parse', 'HEAD')


@pytest.mark.parametrize('tag', ['0.1.0', 'dsh-bundle-0.1.0', 'dsh-bundle-v0.2.0', 'dsh-bundle-v01.0.0'])
def test_invalid_or_mismatched_tag(source, tag):
    with pytest.raises(ValueError):
        module().validate_source(source, tag)


def test_dirty_tracked_tree_rejected(source, release_tag):
    (source / 'integrations/dsh/bundle/README.md').write_text('dirty')
    with pytest.raises(ValueError, match='tracked'):
        module().validate_source(source, release_tag)


def test_commit_must_be_on_main(source, release_tag):
    git(source, 'update-ref', '-d', 'refs/remotes/origin/main')
    with pytest.raises(ValueError, match='main'):
        module().validate_source(source, release_tag)


def test_validate_assets_binds_names_checksum_and_payload(assets, release_tag):
    source, archive, checksum = assets
    assert module().validate_assets(source, archive.parent, release_tag) == [archive, checksum]


@pytest.mark.parametrize('problem', ['checksum', 'extra', 'missing', 'oversized', 'payload', 'tag', 'symlink'])
def test_invalid_asset_directory_rejected(assets, release_tag, problem):
    source, archive, checksum = assets
    if problem == 'checksum':
        checksum.write_text('0' * 64 + '  ' + archive.name + '\n')
    elif problem == 'extra':
        (archive.parent / 'extra.tgz').write_bytes(b'no')
    elif problem == 'missing':
        checksum.unlink()
    elif problem == 'oversized':
        checksum.write_text('0' * 2048)
    elif problem == 'symlink':
        checksum.unlink()
        checksum.symlink_to(archive)
    elif problem == 'payload':
        archive.unlink()
        with tarfile.open(archive, 'w:gz') as output:
            for name in sorted(['package.json', 'cordis.patch.yml', 'README.md', 'LICENSE']):
                data = (source / 'integrations/dsh/bundle' / name).read_bytes()
                if name == 'cordis.patch.yml':
                    data = b'# tampered\n'
                member = tarfile.TarInfo('package/' + name)
                member.size = len(data)
                output.addfile(member, io.BytesIO(data))
        checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    with pytest.raises(ValueError):
        tag = 'dsh-bundle-v0.2.0' if problem == 'tag' else release_tag
        module().validate_assets(source, archive.parent, tag)


def test_private_bundle_identity_rejected(source):
    meta_path = source / 'integrations/dsh/bundle/package.json'
    meta = json.loads(meta_path.read_text())
    meta['private'] = True
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='publishable'):
        module().bundle_metadata(source)


def test_release_workflow_requires_the_public_launcher_pin():
    workflow = (ROOT / '.github/workflows/dsh-bundle-release.yml').read_text(encoding='utf-8')
    assert 'public_install.py --require-launcher' in workflow


def test_check_source_does_not_require_token_or_api(source, release_tag, monkeypatch):
    release = module()
    release.ROOT = source
    monkeypatch.setattr('sys.argv', ['dsh_bundle_release.py', '--release-tag', release_tag, '--check-source'])
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    assert release.main() == 0
