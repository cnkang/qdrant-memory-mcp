/** Host-neutral provisioning. All data operations use the supported Runtime CLI. */
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { mkdir, lstat, readFile, writeFile, rename, rm, realpath, open } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, dirname, parse, resolve, relative, isAbsolute, basename } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { BOOTSTRAPS, UV_VERSION, PYTHON_VERSION, download, extractExecutable, verifyArtifact } from './bootstrap.mjs';

export const runtime = JSON.parse(await readFile(new URL('./runtime.json', import.meta.url), 'utf8'));
export const hosts = new Set(['workbuddy', 'dsh']);
const requirements = (await readFile(new URL('./requirements.lock', import.meta.url), 'utf8')).replaceAll('\r\n', '\n');
export const dependencyDigest = createHash('sha256').update(requirements).update(JSON.stringify(runtime)).digest('hex');
const installedSnapshot = JSON.stringify({ revision: runtime.revision, dependencies: dependencyDigest });

export function runtimeRequirement(artifact, metadata = runtime, lock = requirements) {
  lock = lock.replaceAll('\r\n', '\n');
  if (metadata.status !== 'released-wheel') throw new Error('Unknown Runtime distribution');
  const requirement = `hermes-plugin-qdrant-memory==${metadata.version}`;
  const matches = [...lock.matchAll(/^hermes-plugin-qdrant-memory[^\n]*\n(?:[ \t]+--hash=sha256:[0-9a-f]+(?: \\)?\n)+/gm)];
  if (matches.length !== 1 || !matches[0][0].startsWith(requirement + ' \\\n')
      || !matches[0][0].includes(`--hash=sha256:${metadata.sha256}`)) throw new Error('Runtime dependency lock mismatch');
  // A local wheel has one accepted artifact. Do not retain the registry sdist
  // alternative when installing the downloaded and independently verified wheel.
  return lock.replace(matches[0][0], `hermes-plugin-qdrant-memory @ ${pathToFileURL(artifact).href} \\\n    --hash=sha256:${metadata.sha256}\n`);
}

export function locations(host, env = process.env, home = homedir(), platform = process.platform) {
  if (!hosts.has(host)) throw new Error('Choose workbuddy or dsh');
  const data = platform === 'win32' ? (env.LOCALAPPDATA || join(home, 'AppData', 'Local'))
    : platform === 'darwin' ? join(home, 'Library', 'Application Support')
      : (env.XDG_DATA_HOME || join(home, '.local', 'share'));
  if (!isAbsolute(data)) throw new Error('Managed data root must be absolute');
  const root = env.QDRANT_MEMORY_MANAGED_ROOT || join(data, 'qdrant-memory-managed');
  if (!isAbsolute(root)) throw new Error('Managed root must be absolute');
  return { root, program: join(root, 'programs', runtime.revision, dependencyDigest.slice(0, 12), `${platform}-${process.arch}`),
    profile: join(root, 'profiles', host, 'local'), models: join(root, 'models', runtime.model_revision || runtime.revision) };
}

export async function modelCache(paths) {
  // Keep the cache chosen by an existing profile across program upgrades.
  // Runtime setup still verifies the complete profile ownership/configuration.
  const config = join(paths.profile, 'qdrant-memory.json');
  await privateDirectory(paths.profile);
  try {
    const file = await open(config, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
    let value;
    try {
      const info = await file.stat();
      const entry = await lstat(config);
      if (!info.isFile() || info.size > 65536 || entry.isSymbolicLink()
          || info.ino !== entry.ino || info.dev !== entry.dev) throw new Error('Unsafe profile configuration');
      value = JSON.parse(await file.readFile('utf8'));
    } finally { await file.close(); }
    const cache = value.embedding?.model_cache_dir;
    if (typeof cache !== 'string' || !isAbsolute(cache)) throw new Error('Invalid managed model cache');
    const inside = relative(join(paths.root, 'models'), cache);
    if (!inside || inside.startsWith('..') || isAbsolute(inside)) throw new Error('Model cache escaped managed root');
    await privateDirectory(cache);
    return cache;
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  return paths.models;
}

export async function privateDirectory(path) {
  const absolute = resolve(path);
  let current = parse(absolute).root;
  for (const part of absolute.slice(current.length).split(/[\\/]/).filter(Boolean)) {
    current = join(current, part);
    await mkdir(current, { mode: 0o700 }).catch(error => { if (error.code !== 'EEXIST') throw error; });
    const info = await lstat(current);
    if (info.isSymbolicLink() || !info.isDirectory()) throw new Error('Unsafe managed directory');
    if (process.platform !== 'win32') {
      // A root-owned sticky temporary ancestor may be traversed, never used as
      // the managed directory. Refuse unsafe existing paths without chmod.
      const stickyAncestor = current !== absolute && info.uid === 0 && (info.mode & 0o1000);
      if (!stickyAncestor && ((info.mode & 0o022) ||
          (info.uid !== process.getuid() && !(current !== absolute && info.uid === 0)))) {
        throw new Error('Unsafe managed directory ownership or write permissions');
      }
    }
  }
  return absolute;
}

export function installEnvironment(program, env = process.env) {
  const clean = { PATH: '', UV_NO_CONFIG: '1', UV_CACHE_DIR: join(program, 'cache'),
    UV_PYTHON_INSTALL_DIR: join(program, 'python'), UV_PYTHON_PREFERENCE: 'only-managed',
    UV_PYTHON_DOWNLOADS: 'automatic', UV_NO_PROGRESS: '1', PYTHONNOUSERSITE: '1' };
  for (const name of ['SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR']) if (env[name]) clean[name] = env[name];
  return clean;
}

export function run(executable, args, { env, signal, timeout = 600000 } = {}) {
  return new Promise((accept, reject) => {
    const child = spawn(executable, args, { env, windowsHide: true, detached: process.platform !== 'win32',
      stdio: ['ignore', 'pipe', 'ignore'] });
    let output = '', settled = false;
    const stop = () => {
      if (!child.pid) return;
      if (process.platform === 'win32') {
        // Windows has no POSIX process groups. Use the OS tree-termination utility.
        const systemRoot = process.env.SYSTEMROOT || 'C:\\Windows';
        spawn(join(systemRoot, 'System32', 'taskkill.exe'), ['/pid', String(child.pid), '/T', '/F'],
          { windowsHide: true, stdio: 'ignore' }).unref();
      } else { try { process.kill(-child.pid, 'SIGKILL'); } catch { /* already closed */ } }
    };
    const timer = setTimeout(stop, timeout);
    signal?.addEventListener('abort', stop, { once: true });
    if (signal?.aborted) stop();
    child.stdout.on('data', bytes => { output += bytes; if (output.length > 1024 * 1024) stop(); });
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', stop);
      if (ok && !signal?.aborted) accept(output.trim());
      else reject(new Error('Managed subprocess failed; retry preparation and check network/disk access'));
    };
    child.on('error', () => finish(false));
    child.on('close', code => finish(code === 0));
  });
}

async function regularFile(path) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Unsafe managed file');
  return path;
}

// Windows can briefly hold a freshly written file open: a real-time scan of a
// new executable, or a terminating child that still maps it after a client
// stopped its probe. Retry only transient lock errors, within bounds.
export async function publishRename(from, to, signal) {
  const delays = [50, 100, 200, 400, 800, 1500, 1500, 1500, 1500, 1500];
  for (let attempt = 0; ; attempt++) {
    try {
      await rename(from, to);
      return;
    } catch (error) {
      if (!['EPERM', 'EACCES', 'EBUSY'].includes(error.code) || attempt >= delays.length || signal?.aborted) throw error;
      await new Promise(resolve => setTimeout(resolve, delays[attempt]));
    }
  }
}

// Caller must hold the program's provisioning lock. Only a prefix of the exact
// expected snapshot can be left by an interrupted legacy write; other changes
// remain errors. Publish on the same filesystem only after writing and flushing.
export async function publishSnapshot(path, content) {
  let existing;
  try { await regularFile(path); existing = await readFile(path, 'utf8'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (existing !== undefined && !content.startsWith(existing)) throw new Error(`Managed snapshot changed: ${basename(path)}`);
  const temporary = path + '.pending';
  try { await regularFile(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await rm(temporary, { force: true });
  if (existing === content) return;
  try {
    const file = await open(temporary, 'wx', 0o600);
    try { await file.writeFile(content); await file.sync(); }
    finally { await file.close(); }
    await publishRename(temporary, path);
  } finally { await rm(temporary, { force: true }); }
}

export async function installed(paths) {
  // A marker is committed only after package installation completes. Missing or
  // partial installs are never executable; retries use the same provisioning lock.
  await privateDirectory(paths.program);
  const marker = join(paths.program, 'installed.json');
  await regularFile(marker);
  const value = JSON.parse(await readFile(marker, 'utf8'));
  if (value.revision !== runtime.revision || value.dependencies !== dependencyDigest) throw new Error('Runtime revision or dependency mismatch');
  const executable = join(paths.program, 'env', process.platform === 'win32' ? 'Scripts' : 'bin',
    process.platform === 'win32' ? 'qdrant-memory.exe' : 'qdrant-memory');
  return regularFile(executable);
}

export async function prepare(paths, host, signal, onStage = () => {}) {
  if (!hosts.has(host)) throw new Error('Unknown host');
  await privateDirectory(paths.program);
  const lock = join(paths.program, '.provision.lock');
  // Never steal an old lock: a concurrent installer may still own Python children.
  await mkdir(lock, { mode: 0o700 }).catch(() => { throw new Error('Preparation is already running or interrupted; inspect the provisioning lock'); });
  let stage = 'inspect-installation';
  const enter = value => { stage = value; onStage(value); };
  try {
    let executable;
    try { executable = await installed(paths); } catch (error) {
      if (error instanceof SyntaxError) {
        const marker = join(paths.program, 'installed.json');
        // A truncated legacy marker is not installation success. Retry package
        // validation/installation before committing a new marker; never run it.
        const partial = await readFile(marker, 'utf8');
        if (!installedSnapshot.startsWith(partial)) throw error;
        await rm(marker);
      } else if (error.code !== 'ENOENT') throw error;
    }
    const env = installEnvironment(paths.program);
    if (!executable) {
      const spec = BOOTSTRAPS[`${process.platform}-${process.arch}`];
      if (!spec) throw new Error('Unsupported managed platform');
      const uv = join(paths.program, process.platform === 'win32' ? 'uv.exe' : 'uv');
      enter('download-bootstrap');
      // Publish only a fully verified regular executable, never an archive path.
      const bytes = extractExecutable(await download(spec, signal), `uv-${UV_VERSION}.data/scripts/${process.platform === 'win32' ? 'uv.exe' : 'uv'}`);
      const temporary = uv + '.pending';
      // A stopped probe can leave a stale temporary file; the held lock makes removal safe.
      await rm(temporary, { force: true });
      await writeFile(temporary, bytes, { flag: 'wx', mode: 0o700 });
      if (await lstat(uv).catch(error => { if (error.code !== 'ENOENT') throw error; })) await regularFile(uv);
      await publishRename(temporary, uv, signal);
      enter('install-python');
      await run(uv, ['python', 'install', PYTHON_VERSION, '--no-bin'], { env, signal });
      const python = await run(uv, ['python', 'find', '--system', PYTHON_VERSION], { env, signal });
      const inside = relative(await realpath(paths.program), await realpath(python));
      if (!inside || inside.startsWith('..') || isAbsolute(inside)) throw new Error('Python escaped managed root');
      // A client may stop a probe after discovery, interrupting preparation.
      // Resume only this revision-owned environment; never clear its contents.
      await run(uv, ['venv', '--allow-existing', '--python', python, join(paths.program, 'env')], { env, signal });
      enter('download-runtime');
      const archive = join(paths.program, `hermes_plugin_qdrant_memory-${runtime.version}-py3-none-any.whl`);
      // Clear an interrupted temporary download even if the verified artifact
      // survived. The provisioning lock owns only this program transaction.
      await rm(archive + '.pending', { force: true });
      try { await regularFile(archive); verifyArtifact(await readFile(archive), runtime); }
      catch (error) {
        if (error.code !== 'ENOENT') throw error;
        // Publish the archive only after the full download is on disk, so an
        // interrupted write can never leave a partial archive that blocks retries.
        const temporaryArchive = archive + '.pending';
        await rm(temporaryArchive, { force: true });
        await writeFile(temporaryArchive, await download(runtime, signal), { mode: 0o600 });
        await publishRename(temporaryArchive, archive, signal);
      }
      const environmentPython = join(paths.program, 'env', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
      // Install only published wheels. No source builds or build environment.
      const resolvedRequirements = runtimeRequirement(archive);
      const lockfile = join(paths.program, 'requirements.lock');
      await publishSnapshot(lockfile, resolvedRequirements);
      enter('install-runtime');
      await run(uv, ['pip', 'install', '--python', environmentPython, '--no-deps', '--no-build-isolation', '--require-hashes',
        '--only-binary=:all:',
        '-r', lockfile], { env, signal });
      await run(uv, ['pip', 'check', '--python', environmentPython], { env, signal });
      await rm(archive);
      await publishSnapshot(join(paths.program, 'installed.json'), installedSnapshot);
      executable = await installed(paths);
    }
    await privateDirectory(dirname(paths.profile));
    const models = await modelCache(paths);
    await privateDirectory(models);
    enter('setup-profile');
    await run(executable, ['setup', '--profile', paths.profile, '--embedding-provider', 'fastembed',
      '--model-cache-dir', models, '--agent-id', host], { env, signal });
    return executable;
  } catch (error) {
    error.stage = stage;
    throw error;
  } finally { await rm(lock, { recursive: true }); }
}
