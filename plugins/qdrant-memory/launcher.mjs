/** Codex's portable stdio entrypoint. Python Runtime owns every memory operation. */
import { spawn, spawnSync } from 'node:child_process';
import { access, lstat, readFile, realpath } from 'node:fs/promises';
import { constants } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function locations(env = process.env, home = homedir(), platform = process.platform) {
  const root = env.QDRANT_MEMORY_CODEX_ROOT || join(home, '.qdrant-memory', 'codex');
  const profile = env.QDRANT_MEMORY_CODEX_PROFILE || join(root, 'profile');
  const executable = env.QDRANT_MEMORY_CODEX_EXECUTABLE || join(root, 'runtime',
    platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'qdrant-memory.exe' : 'qdrant-memory');
  const python = env.QDRANT_MEMORY_CODEX_PYTHON || join(dirname(executable),
    platform === 'win32' ? 'python.exe' : 'python');
  if (![root, profile, executable, python].every(isAbsolute)) throw new Error('Absolute paths required');
  return { root, profile, executable, python };
}

/** Refuse to start with an MCP distribution that differs from this plugin pin. */
export function assertMcpVersion(release, installed) {
  if (installed !== release.mcp_distribution_version) {
    throw new Error('Installed MCP version does not match the plugin pin. Run the setup skill to refresh the pinned environment.');
  }
}

/** Read the installed MCP version from this virtual environment and validate it. */
async function verifyMcpVersion(paths) {
  const release = JSON.parse(await readFile(new URL('./release.json', import.meta.url), 'utf8'));
  const script = [
    'import importlib.metadata as metadata, json, sysconfig',
    'print(json.dumps({"version": metadata.version("qdrant-memory-mcp"), "scripts": sysconfig.get_path("scripts")}))',
  ].join('\n');
  const result = spawnSync(paths.python, ['-c', script], {
    encoding: 'utf8', timeout: 10000, maxBuffer: 256 * 1024, windowsHide: true,
    env: { ...process.env, PYTHONNOUSERSITE: '1', PYTHONPATH: '', PYTHONHOME: '' },
  });
  if (result.error || result.status !== 0) {
    throw new Error('Could not verify the pinned MCP package. Run the setup skill to refresh the pinned environment.');
  }
  const installed = JSON.parse(result.stdout);
  assertMcpVersion(release, installed.version);
  const executableName = process.platform === 'win32' ? 'qdrant-memory.exe' : 'qdrant-memory';
  let configuredExecutable;
  let pinnedEnvironmentExecutable;
  try {
    [configuredExecutable, pinnedEnvironmentExecutable] = await Promise.all([
      realpath(paths.executable),
      realpath(join(installed.scripts, executableName)),
    ]);
  } catch {
    throw new Error('Could not bind the MCP executable to the Python environment used for version verification.');
  }
  if (configuredExecutable !== pinnedEnvironmentExecutable) {
    throw new Error('MCP executable and Python interpreter must come from the same environment.');
  }
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
  // POSIX virtual environments commonly expose Python through a symlink.
  await access(paths.python, constants.X_OK);
  await verifyMcpVersion(paths);
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
    console.error('Qdrant Memory is not ready. Run the setup skill to install or update the pinned Python environment; check Node, Python, profile and WriterLease. No data was reset.'
      + ` Explicit executable: ${Boolean(process.env.QDRANT_MEMORY_CODEX_EXECUTABLE)}; explicit profile: ${Boolean(process.env.QDRANT_MEMORY_CODEX_PROFILE)}.`);
    process.exitCode = 1;
  }
}
