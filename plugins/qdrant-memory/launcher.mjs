/** Codex's portable stdio entrypoint. Python Runtime owns every memory operation. */
import { spawn } from 'node:child_process';
import { access, lstat, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function locations(env = process.env, home = homedir(), platform = process.platform) {
  const root = env.QDRANT_MEMORY_CODEX_ROOT || join(home, '.qdrant-memory', 'codex');
  const profile = env.QDRANT_MEMORY_CODEX_PROFILE || join(root, 'profile');
  const executable = env.QDRANT_MEMORY_CODEX_EXECUTABLE || join(root, 'runtime',
    platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'qdrant-memory.exe' : 'qdrant-memory');
  if (![root, profile, executable].every(isAbsolute)) throw new Error('Absolute paths required');
  return { root, profile, executable };
}

async function canonical(path) {
  let current = resolve(path);
  while (true) {
    try { if ((await lstat(current)).isSymbolicLink()) throw new Error('Symlink refused'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    const parent = dirname(current);
    if (parent === current) return;
    current = parent;
  }
}

export async function launch(mode, env = process.env) {
  if (!['doctor', 'mcp'].includes(mode)) throw new Error('Choose doctor or mcp');
  const paths = locations(env);
  await canonical(paths.executable);
  await canonical(paths.profile);
  await access(paths.executable, constants.X_OK);
  const owner = env.QDRANT_MEMORY_CODEX_OWNER_URL;
  if (!owner) {
    await canonical(join(paths.profile, 'qdrant-memory.json'));
    const cfg = JSON.parse(await readFile(join(paths.profile, 'qdrant-memory.json'), 'utf8'));
    if (!cfg.scope?.user_id) throw new Error('Configure an isolated profile first');
  }
  const args = owner
    ? ['shared-mcp', '--url', owner, '--token-env', 'QDRANT_MEMORY_SHARED_TOKEN']
    : ['--home', paths.profile, mode === 'doctor' ? 'doctor' : 'mcp'];
  if (mode === 'doctor' && owner) throw new Error('Use Runtime shared-doctor with the approved policy');
  const child = spawn(paths.executable, args, { stdio: 'inherit', windowsHide: true,
    env: { ...env, PYTHONNOUSERSITE: '1', PYTHONPATH: '', PYTHONHOME: '' } });
  const stop = signal => child.kill(signal);
  const term = () => stop('SIGTERM');
  const interrupt = () => stop('SIGINT');
  process.once('SIGTERM', term);
  process.once('SIGINT', interrupt);
  try {
    return await new Promise((resolve, reject) => {
      child.once('error', reject);
      child.once('exit', (code, signal) => resolve(signal ? 1 : code ?? 1));
    });
  } finally {
    process.removeListener('SIGTERM', term);
    process.removeListener('SIGINT', interrupt);
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { process.exitCode = await launch(process.argv[2] || 'mcp'); }
  catch {
    console.error('Qdrant Memory is not ready. Run the plugin setup skill; check Node, the pinned Runtime, profile and WriterLease. No data was reset.'
      + ` Explicit executable: ${Boolean(process.env.QDRANT_MEMORY_CODEX_EXECUTABLE)}; explicit profile: ${Boolean(process.env.QDRANT_MEMORY_CODEX_PROFILE)}.`);
    process.exitCode = 1;
  }
}
