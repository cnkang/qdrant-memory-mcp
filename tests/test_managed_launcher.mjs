import test, { mock } from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import filesystem from 'node:fs/promises';
import { syncBuiltinESMExports } from 'node:module';
import { mkdtemp, mkdir, symlink, rm, realpath, writeFile, readFile, lstat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { bridge, tools } from '../integrations/managed/bridge.mjs';
import { locations, installEnvironment, privateDirectory, run, installed, prepare,
  publishSnapshot, runtime, dependencyDigest } from '../integrations/managed/provision.mjs';

test('installation snapshots replace interrupted writes but reject changed contents and unsafe paths', async () => {
  const root = await mkdtemp(join(await realpath(tmpdir()), 'memory-snapshot-'));
  const path = join(root, 'requirements.lock');
  const expected = 'pinned-runtime==1.0 --hash=sha256:verified\n';
  try {
    for (const partial of ['', expected.slice(0, 15), expected]) {
      await writeFile(path, partial);
      await writeFile(path + '.pending', 'interrupted temporary write');
      await publishSnapshot(path, expected);
      assert.equal(await readFile(path, 'utf8'), expected);
    }
    await writeFile(path, 'unexpected-package==2');
    await assert.rejects(publishSnapshot(path, expected), /snapshot changed/);
    assert.equal(await readFile(path, 'utf8'), 'unexpected-package==2');
    await rm(path);
    await symlink(join(root, 'target'), path, process.platform === 'win32' ? 'junction' : 'file');
    await assert.rejects(publishSnapshot(path, expected), /Unsafe/);
    assert.ok((await lstat(path)).isSymbolicLink(), 'the symlink remains in place');
    await assert.rejects(lstat(join(root, 'target')), { code: 'ENOENT' });
    await rm(path);
    await mkdir(path);
    await assert.rejects(publishSnapshot(path, expected), /Unsafe/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('a failed snapshot write never publishes partial contents and can be retried', async () => {
  const root = await mkdtemp(join(await realpath(tmpdir()), 'memory-write-failure-'));
  const path = join(root, 'installed.json');
  const expected = '{"revision":"verified","dependencies":"verified"}';
  const originalOpen = filesystem.open;
  try {
    await writeFile(path, expected.slice(0, 10));
    const mocked = mock.method(filesystem, 'open', async (...args) => {
      const file = await originalOpen(...args);
      return {
        async writeFile(content) {
          await file.writeFile(content.slice(0, 3));
          throw Object.assign(new Error('synthetic disk full'), { code: 'ENOSPC' });
        },
        close: () => file.close(),
      };
    });
    syncBuiltinESMExports();
    try { await assert.rejects(publishSnapshot(path, expected), { code: 'ENOSPC' }); }
    finally { mocked.mock.restore(); syncBuiltinESMExports(); }
    assert.equal(await readFile(path, 'utf8'), expected.slice(0, 10));
    await assert.rejects(lstat(path + '.pending'), { code: 'ENOENT' });
    await publishSnapshot(path, expected);
    assert.equal(await readFile(path, 'utf8'), expected);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('preparation recovers truncated markers only while holding its installation lock', async () => {
  const root = await mkdtemp(join(await realpath(tmpdir()), 'memory-marker-'));
  const paths = { program: root, profile: join(root, 'profile'), models: join(root, 'models') };
  const marker = join(root, 'installed.json');
  const expected = JSON.stringify({ revision: runtime.revision, dependencies: dependencyDigest });
  const stop = stage => { if (stage === 'download-bootstrap') throw new Error('test stops before network'); };
  try {
    for (const partial of ['', expected.slice(0, 20)]) {
      await writeFile(marker, partial);
      await assert.rejects(installed(paths), SyntaxError);
      await mkdir(join(root, '.provision.lock'));
      await assert.rejects(prepare(paths, 'dsh', undefined, stop), /already running/);
      assert.equal(await readFile(marker, 'utf8'), partial);
      await rm(join(root, '.provision.lock'), { recursive: true });
      for (let attempt = 0; attempt < 2; attempt++) {
        await assert.rejects(prepare(paths, 'dsh', undefined, stop), error =>
          error.stage === 'download-bootstrap' && error.message === 'test stops before network');
        await assert.rejects(lstat(marker), { code: 'ENOENT' });
      }
    }
    await writeFile(marker, JSON.stringify({ revision: 'different', dependencies: dependencyDigest }));
    await assert.rejects(prepare(paths, 'dsh', undefined, stop), /revision or dependency mismatch/);
    await writeFile(marker, '{"unrecognized":');
    await assert.rejects(prepare(paths, 'dsh', undefined, stop), SyntaxError);
    assert.equal(await readFile(marker, 'utf8'), '{"unrecognized":');
    await assert.rejects(lstat(paths.profile), { code: 'ENOENT' });
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('host profiles are isolated on each platform and program/cache are shared', () => {
  for (const platform of ['darwin', 'win32', 'linux']) {
    // Use native absolute paths while exercising each platform's routing logic.
    const env = { LOCALAPPDATA: tmpdir(), XDG_DATA_HOME: tmpdir() };
    const a = locations('workbuddy', env, tmpdir(), platform);
    const b = locations('dsh', env, tmpdir(), platform);
    assert.notEqual(a.profile, b.profile);
    assert.equal(a.program, b.program);
    assert.equal(a.models, b.models);
    assert.ok(!a.profile.includes('.hermes'));
  }
  assert.throws(() => locations('hermes'));
  assert.throws(() => locations('dsh', { QDRANT_MEMORY_MANAGED_ROOT: 'relative' }));
});

test('installer subprocesses never inherit service secrets or Python injection', () => {
  const env = installEnvironment(tmpdir(), { QDRANT_API_KEY: 'sentinel', EMBEDDING_API_KEY: 'sentinel',
    PATH: 'untrusted', PYTHONPATH: 'untrusted', UV_INDEX_URL: 'untrusted', TOKEN: 'sentinel' });
  assert.equal(env.PATH, '');
  assert.ok(!JSON.stringify(env).includes('sentinel'));
  assert.ok(!JSON.stringify(env).includes('untrusted'));
});

test('managed paths reject symlink destinations', async () => {
  const root = await mkdtemp(join(tmpdir(), 'memory-path-'));
  try {
    await mkdir(join(root, 'real'));
    await symlink(join(root, 'real'), join(root, 'link'), process.platform === 'win32' ? 'junction' : 'dir');
    await assert.rejects(privateDirectory(join(root, 'link', 'child')), /Unsafe/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('handshake and discovery stay responsive during cold setup; writes never queue', async () => {
  const input = new PassThrough(), output = new PassThrough();
  const received = [];
  output.on('data', bytes => received.push(...bytes.toString().trim().split('\n').map(JSON.parse)));
  let aborted = false;
  const done = bridge(signal => new Promise((_, reject) => signal.addEventListener('abort', () => {
    aborted = true; reject(new Error('synthetic secret must not appear'));
  })), input, output);
  for (const [id, method, params] of [[1, 'initialize', { protocolVersion: '2025-11-25' }],
    [2, 'tools/list', {}], [3, 'tools/call', { name: 'qdrant_memory_add', arguments: { text: 'never queued' } }]]) {
    input.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
  }
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(received[0].result.serverInfo.name, 'qdrant-memory-managed');
  assert.deepEqual(received[1].result.tools, tools);
  assert.equal(received[2].result.isError, true);
  assert.match(received[2].result.content[0].text, /No operation/);
  input.end();
  await done;
  assert.equal(aborted, true);
  assert.ok(!JSON.stringify(received).includes('synthetic secret'));
});

test('preparation errors remain bounded and redact raw subprocess details', async () => {
  const input = new PassThrough(), output = new PassThrough();
  let text = '';
  output.on('data', bytes => { text += bytes; });
  const done = bridge(async () => { throw new Error('synthetic-key-private-profile'); }, input, output);
  await new Promise(resolve => setImmediate(resolve));
  input.write(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize' }) + '\n');
  input.write(JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call' }) + '\n');
  await new Promise(resolve => setImmediate(resolve));
  input.end(); await done;
  assert.match(text, /preparation failed/);
  assert.ok(!text.includes('synthetic-key'));
  await assert.rejects(run(process.execPath, ['-e', 'process.stderr.write("private-token"); process.exit(1)']),
    error => !error.message.includes('private-token'));
});
