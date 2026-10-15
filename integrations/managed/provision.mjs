/** Host-neutral provisioning. All data operations use the supported Runtime CLI. */
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, lstat, readFile, writeFile, rename, rm, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, dirname, parse, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { BOOTSTRAPS, UV_VERSION, PYTHON_VERSION, download, extractExecutable, verifyArtifact } from './bootstrap.mjs';

export const runtime = JSON.parse(await readFile(new URL('./runtime.json', import.meta.url), 'utf8'));
export const hosts = new Set(['workbuddy', 'dsh']);
const requirements = await readFile(new URL('./requirements.lock', import.meta.url), 'utf8');
const buildRequirements = await readFile(new URL('./build-requirements.lock', import.meta.url), 'utf8');
export const dependencyDigest = createHash('sha256').update(requirements).update(buildRequirements).digest('hex');

export function locations(host, env = process.env, home = homedir(), platform = process.platform) {
  if (!hosts.has(host)) throw new Error('Choose workbuddy or dsh');
  const data = platform === 'win32' ? (env.LOCALAPPDATA || join(home, 'AppData', 'Local'))
    : platform === 'darwin' ? join(home, 'Library', 'Application Support')
      : (env.XDG_DATA_HOME || join(home, '.local', 'share'));
  if (!isAbsolute(data)) throw new Error('Managed data root must be absolute');
  const root = env.QDRANT_MEMORY_MANAGED_ROOT || join(data, 'qdrant-memory-managed');
  if (!isAbsolute(root)) throw new Error('Managed root must be absolute');
  return { root, program: join(root, 'programs', runtime.revision, dependencyDigest.slice(0, 12), `${platform}-${process.arch}`),
    profile: join(root, 'profiles', host, 'local'), models: join(root, 'models', runtime.revision) };
}

export async function privateDirectory(path) {
  const absolute = resolve(path);
  let current = parse(absolute).root;
  for (const part of absolute.slice(current.length).split(/[\\/]/).filter(Boolean)) {
    current = join(current, part);
    await mkdir(current, { mode: 0o700 }).catch(error => { if (error.code !== 'EEXIST') throw error; });
    const info = await lstat(current);
    if (info.isSymbolicLink() || !info.isDirectory()) throw new Error('Unsafe managed directory');
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
    try { executable = await installed(paths); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const env = installEnvironment(paths.program);
    if (!executable) {
      const spec = BOOTSTRAPS[`${process.platform}-${process.arch}`];
      if (!spec) throw new Error('Unsupported managed platform');
      const uv = join(paths.program, process.platform === 'win32' ? 'uv.exe' : 'uv');
      enter('download-bootstrap');
      // Publish only a fully verified regular executable, never an archive path.
      const bytes = extractExecutable(await download(spec, signal), `uv-${UV_VERSION}.data/scripts/${process.platform === 'win32' ? 'uv.exe' : 'uv'}`);
      const temporary = uv + '.pending';
      await writeFile(temporary, bytes, { flag: 'wx', mode: 0o700 });
      if (await lstat(uv).catch(error => { if (error.code !== 'ENOENT') throw error; })) await regularFile(uv);
      await rename(temporary, uv);
      enter('install-python');
      await run(uv, ['python', 'install', PYTHON_VERSION, '--no-bin'], { env, signal });
      const python = await run(uv, ['python', 'find', '--system', PYTHON_VERSION], { env, signal });
      const inside = relative(await realpath(paths.program), await realpath(python));
      if (!inside || inside.startsWith('..') || isAbsolute(inside)) throw new Error('Python escaped managed root');
      // A client may stop a probe after discovery, interrupting preparation.
      // Resume only this revision-owned environment; never clear its contents.
      await run(uv, ['venv', '--allow-existing', '--python', python, join(paths.program, 'env')], { env, signal });
      enter('download-runtime');
      const archive = join(paths.program, 'runtime.tar.gz');
      try { await regularFile(archive); verifyArtifact(await readFile(archive), runtime); }
      catch (error) {
        if (error.code !== 'ENOENT') throw error;
        await writeFile(archive, await download(runtime, signal), { flag: 'wx', mode: 0o600 });
      }
      const environmentPython = join(paths.program, 'env', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
      // Install locked wheel-only build tools, then build the one verified Runtime
      // archive without an unpinned PEP 517 build environment.
      enter('install-build-tools');
      await run(uv, ['pip', 'install', '--python', environmentPython, '--no-deps', '--require-hashes', '--only-binary=:all:',
        '-r', fileURLToPath(new URL('./build-requirements.lock', import.meta.url))], { env, signal });
      const sourceURL = `https://github.com/cnkang/hermes-plugin-qdrant-memory/archive/${runtime.revision}.tar.gz`;
      if (!requirements.includes(sourceURL) || !requirements.includes(runtime.sha256)) throw new Error('Runtime dependency lock mismatch');
      const resolvedRequirements = requirements.replace(sourceURL, pathToFileURL(archive).href);
      const lockfile = join(paths.program, 'requirements.lock');
      try {
        await regularFile(lockfile);
        if (await readFile(lockfile, 'utf8') !== resolvedRequirements) throw new Error('Managed requirement snapshot changed');
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
        await writeFile(lockfile, resolvedRequirements, { flag: 'wx', mode: 0o600 });
      }
      enter('install-runtime');
      await run(uv, ['pip', 'install', '--python', environmentPython, '--no-deps', '--no-build-isolation', '--require-hashes',
        '-r', lockfile], { env, signal });
      await run(uv, ['pip', 'check', '--python', environmentPython], { env, signal });
      await rm(archive);
      await writeFile(join(paths.program, 'installed.json'), JSON.stringify({ revision: runtime.revision, dependencies: dependencyDigest }), { flag: 'wx', mode: 0o600 });
      executable = await installed(paths);
    }
    await privateDirectory(dirname(paths.profile));
    await privateDirectory(paths.models);
    enter('setup-profile');
    await run(executable, ['setup', '--profile', paths.profile, '--embedding-provider', 'fastembed',
      '--model-cache-dir', paths.models, '--agent-id', host], { env, signal });
    return executable;
  } catch (error) {
    error.stage = stage;
    throw error;
  } finally { await rm(lock, { recursive: true }); }
}
