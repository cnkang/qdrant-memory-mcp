#!/usr/bin/env python3
"""Validate a merged annotated snapshot and attach assets before publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests

import tomllib

ROOT = Path(__file__).resolve().parents[2]
SEMVER = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


def validate_source(root: Path, tag: str, main_ref: str = 'refs/remotes/origin/main') -> tuple[str, str]:
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    if not re.fullmatch('v' + SEMVER, tag) or tag != 'v' + version:
        raise ValueError('Release tag must be vSemVer matching pyproject.toml version')
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
    return sha, f'WorkBuddy connector assets for {tag}. Publication remains a maintainer decision.'


def validate_assets(root: Path, directory: Path, tag: str) -> list[Path]:
    """Check the already-built artifact; never execute or import a builder."""
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    config = root / 'integrations/workbuddy'
    meta = json.loads((config / 'connector-meta.json').read_text(encoding='utf-8'))
    skill = json.loads((config / 'skill-source.json').read_text(encoding='utf-8'))
    version = project['version']
    connector = meta['version']
    if tag != 'v' + version or not re.fullmatch(SEMVER, connector):
        raise ValueError('Asset versions do not match release metadata')
    runtime = [re.fullmatch(r'hermes-plugin-qdrant-memory\[mcp\]==(.+)', dependency)
               for dependency in project.get('dependencies', [])]
    runtime = [match.group(1) for match in runtime if match]
    if len(runtime) != 1:
        raise ValueError('Expected exactly one pinned runtime dependency')
    if json.loads((root / 'runtime-source.json').read_text(encoding='utf-8'))['version'] != runtime[0]:
        raise ValueError('Pinned runtime does not match runtime-source.json')
    name = f'qdrant-memory-workbuddy-connector-v{connector}-mcp-v{version}.zip'
    if any(path.is_symlink() for path in [directory, *directory.parents]) or not directory.is_dir():
        raise ValueError('Asset directory must be a real directory')
    paths = [directory / name, directory / (name + '.sha256')]
    if {entry.name for entry in directory.iterdir()} != {path.name for path in paths}:
        raise ValueError('Asset directory must contain exactly the expected ZIP and checksum')
    for path, maximum in zip(paths, [32 * 1024 * 1024, 1024]):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise ValueError('Assets must be bounded regular files without symlinks')
    digest = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    if paths[1].read_text(encoding='utf-8') != f'{digest}  {name}\n':
        raise ValueError('Asset checksum or checksum filename does not match')
    expected = {'connector_version': connector, 'mcp_version': version,
                'runtime_version': runtime[0], 'skill_version': skill['version'],
                'skill_repository': skill['repository'], 'skill_commit': skill['commit'],
                'release_tag': tag}
    try:
        with zipfile.ZipFile(paths[0]) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)) or not names:
                raise ValueError('Archive has duplicate or missing members')
            for member in members:
                parts = member.filename.split('/')
                if (parts[0] != 'qdrant-memory-workbuddy' or len(parts) < 2
                        or any(part in ('', '.', '..') for part in parts)
                        or '\\' in member.filename
                        or stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG)):
                    raise ValueError('Archive must have a safe qdrant-memory-workbuddy/ root')
            if sum(member.file_size for member in members) > 64 * 1024 * 1024:
                raise ValueError('Archive uncompressed size is too large')
            required = ['icon.svg', 'skills/qdrant-memory/LICENSE', 'skills/qdrant-memory/SKILL.md']
            if any('qdrant-memory-workbuddy/' + name not in names for name in required):
                raise ValueError('Archive must include icon, Skill LICENSE and SKILL.md as regular files')
            provenance_name = 'qdrant-memory-workbuddy/provenance.json'
            if archive.getinfo(provenance_name).file_size > 65536:
                raise ValueError('Archive provenance is too large')
            if json.loads(archive.read(provenance_name)) != expected:
                raise ValueError('Archive provenance does not match checked-out release inputs')
            for filename in ('connector-meta.json', 'mcp.json'):
                member = 'qdrant-memory-workbuddy/' + filename
                if archive.getinfo(member).file_size > 65536:
                    raise ValueError('Archive manifest is too large')
                checked_in = config / filename
                if checked_in.is_symlink():
                    raise ValueError('Archive launch inputs must not be symlinks')
                if filename == 'connector-meta.json':
                    value = meta
                else:
                    value = json.loads(checked_in.read_text(encoding='utf-8'))
                if json.loads(archive.read(member)) != value:
                    raise ValueError('Archive manifest or launch config does not match checked-out inputs')
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid release ZIP or provenance') from exc
    return paths


class GitHubAPI:
    """Small REST adapter; only create-draft and upload are write operations."""
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid GitHub repository')
        self.base = f'https://api.github.com/repos/{repository}'
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {token}',
                                     'Accept': 'application/vnd.github+json',
                                     'X-GitHub-Api-Version': '2022-11-28'})

    def request(self, method, url, **kwargs):
        try:
            response = self.session.request(method, url, timeout=120, **kwargs)
        except requests.RequestException:
            raise ValueError(f'GitHub {method} failed: network request error; inspect the workflow and retry without replacing assets') from None
        if not response.ok:
            # Do not print response bodies, authentication or release contents.
            raise ValueError(f'GitHub {method} failed: HTTP {response.status_code}; inspect the workflow and retry without replacing assets')
        return response

    def pages(self, url):
        page = 1
        result = []
        while True:
            items = self.request('GET', url, params={'per_page': 100, 'page': page}).json()
            result.extend(items)
            if len(items) < 100:
                return result
            page += 1

    def verify_tag(self, tag, sha):
        """Prevent create-release from implicitly creating a remote tag."""
        obj = self.request('GET', f'{self.base}/git/ref/tags/{quote(tag, safe="")}').json()['object']
        for _ in range(8):
            if obj['type'] == 'commit':
                if obj['sha'] != sha:
                    raise ValueError('Remote tag does not match validated source commit; do not move the tag')
                return
            if obj['type'] != 'tag' or not re.fullmatch(r'[0-9a-f]{40,64}', obj['sha']):
                break
            obj = self.request('GET', f'{self.base}/git/tags/{obj["sha"]}').json()['object']
        raise ValueError('Remote tag must resolve to the validated commit')

    def find_release(self, tag):
        matches = [r for r in self.pages(f'{self.base}/releases') if r['tag_name'] == tag]
        if len(matches) > 1:
            raise ValueError('Multiple releases for this tag; maintainer must resolve manually')
        return matches[0] if matches else None

    def create_draft(self, tag, sha, notes):
        return self.request('POST', f'{self.base}/releases', json={
            'tag_name': tag, 'target_commitish': sha, 'name': tag,
            'body': notes, 'draft': True, 'prerelease': False,
        }).json()

    def get_release(self, release_id):
        return self.request('GET', f'{self.base}/releases/{release_id}').json()

    def list_assets(self, release_id):
        return self.pages(f'{self.base}/releases/{release_id}/assets')

    def download_asset(self, asset):
        # API asset URLs are derived from IDs, not release-supplied arbitrary URLs.
        return self.request('GET', f'{self.base}/releases/assets/{asset["id"]}',
                            headers={'Accept': 'application/octet-stream'}).content

    def upload_asset(self, release, path):
        url = self.base.replace('api.github.com', 'uploads.github.com')
        url += f'/releases/{release["id"]}/assets?name={quote(path.name, safe="")}'
        with path.open('rb') as stream:
            self.request('POST', url, data=stream, headers={'Content-Type': 'application/octet-stream'})


def attach_assets(api, tag: str, sha: str, notes: str, paths: list[Path]) -> None:
    api.verify_tag(tag, sha)
    release = api.find_release(tag)
    if release is None:
        release = api.create_draft(tag, sha, notes)
    if release['tag_name'] != tag:
        raise ValueError('Release tag mismatch')
    assets = api.list_assets(release['id'])
    missing = []
    # Preflight the entire catalog before uploading any missing asset.
    for path in paths:
        matches = [a for a in assets if a['name'] == path.name]
        if len(matches) > 1:
            raise ValueError(f'Duplicate release asset: {path.name}')
        if matches:
            if api.download_asset(matches[0]) != path.read_bytes():
                raise ValueError(f'Release asset differs: {path.name}; preserve it and investigate source/toolchain; use a new approved snapshot if necessary')
        else:
            missing.append(path)
    if missing and (not release['draft'] or release.get('immutable', False)):
        raise ValueError('Published release is missing WorkBuddy assets; do not overwrite or move its tag. Prepare a new approved snapshot and draft release')
    for path in missing:
        # A maintainer may have published since the preflight. Never knowingly
        # add assets after publication, even when immutability is disabled.
        current = api.get_release(release['id'])
        if not current['draft'] or current.get('immutable', False) or current['tag_name'] != tag:
            raise ValueError('Release left Draft state during upload; inspect manually')
        api.upload_asset(current, path)
    final = api.list_assets(release['id'])
    for path in paths:
        matches = [a for a in final if a['name'] == path.name]
        if len(matches) != 1 or api.download_asset(matches[0]) != path.read_bytes():
            raise ValueError(f'Uploaded asset verification failed: {path.name}; retry the same tag after investigating')
    print(f'All {len(paths)} release assets verified; publication remains a maintainer decision')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-tag', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-source', action='store_true')
    group.add_argument('--asset-dir', type=Path)
    args = parser.parse_args()
    sha, notes = validate_source(ROOT, args.release_tag)
    if args.check_source:
        print(f'Validated merged release: {args.release_tag} ({sha})')
        return 0
    paths = validate_assets(ROOT, args.asset_dir, args.release_tag)
    api = GitHubAPI(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'])
    attach_assets(api, args.release_tag, sha, notes, paths)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'WorkBuddy release failed: {exc}')
