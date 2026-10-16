"""Validate a merged DSH bundle snapshot and attach assets before publication."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = 'dsh-bundle-v'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


def bundle_metadata(root: Path) -> dict:
    meta = json.loads((root / 'integrations/dsh/bundle/package.json').read_text(encoding='utf-8'))
    if meta.get('private') or not re.fullmatch(r'@[a-z0-9-]+/[a-z0-9-]+', meta.get('name', '')) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', meta.get('version', '')):
        raise ValueError('Bundle package identity is not publishable')
    return meta


def validate_source(root: Path, tag: str, main_ref: str = 'refs/remotes/origin/main') -> tuple[str, str]:
    meta = bundle_metadata(root)
    if tag != TAG + meta['version']:
        raise ValueError(f'Release tag must be {TAG}{meta["version"]}')
    try:
        sha = git(root, 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}')
    except subprocess.CalledProcessError:
        raise ValueError('Release requires an existing tag; create it only through the approved release process') from None
    if git(root, 'rev-parse', 'HEAD') != sha:
        raise ValueError('Current checkout does not match release tag commit')
    if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', sha, main_ref], capture_output=True).returncode:
        raise ValueError('Release commit is not merged into main')
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Release checkout has tracked changes')
    return sha, f'DSH bundle assets for {tag}. Publication remains a maintainer decision.'


def validate_assets(root: Path, directory: Path, tag: str) -> list[Path]:
    """Check the already-built artifact; never publish an unreviewed payload."""
    meta = bundle_metadata(root)
    if tag != TAG + meta['version']:
        raise ValueError('Asset version does not match release tag')
    filename = meta['name'].removeprefix('@').replace('/', '-') + '-' + meta['version'] + '.tgz'
    if any(path.is_symlink() for path in [directory, *directory.parents]) or not directory.is_dir():
        raise ValueError('Asset directory must be a real directory')
    archive = directory / filename
    checksum = directory / (filename + '.sha256')
    if {entry.name for entry in directory.iterdir()} != {archive.name, checksum.name}:
        raise ValueError('Asset directory must contain exactly the expected tgz and checksum')
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Archive must be a bounded regular file without symlinks')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if checksum.read_text(encoding='utf-8') != f'{digest}  {filename}\n':
        raise ValueError('Asset checksum or checksum filename does not match')
    packer = load_module('pack_dsh_bundle', root / 'scripts/pack_dsh_bundle.py')
    if packer.inspect(archive, root / 'integrations/dsh/bundle') != digest:
        raise ValueError('Archive payload differs from the reviewed bundle source')
    return [archive, checksum]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-tag', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-source', action='store_true')
    group.add_argument('--asset-dir', type=Path)
    args = parser.parse_args()
    sha, notes = validate_source(ROOT, args.release_tag)
    if args.check_source:
        print(f'Validated merged bundle release: {args.release_tag} ({sha})')
        return 0
    paths = validate_assets(ROOT, args.asset_dir, args.release_tag)
    release = load_module('workbuddy_release', ROOT / 'integrations/workbuddy/release.py')
    api = release.GitHubAPI(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'])
    release.attach_assets(api, args.release_tag, sha, notes, paths)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'DSH bundle release failed: {exc}')
