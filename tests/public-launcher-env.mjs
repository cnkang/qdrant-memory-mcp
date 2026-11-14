import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PUBLIC_NPM_REGISTRY = 'https://registry.npmjs.org/';
const CREDENTIAL_ENV_NAME = /(token|key|secret|password|passwd|credential|auth|cookie)/i;
const ACCEPTANCE_CHILD_ENV_KEYS = new Set([
  'path', 'systemroot', 'windir', 'comspec', 'pathext', 'systemdrive',
]);

/** Copy only OS process-launch variables; callers supply isolated paths explicitly. */
export function createAcceptanceChildEnvironment(sourceEnv, overrides = {}) {
  if (Object.keys(overrides).some(key => CREDENTIAL_ENV_NAME.test(key))) {
    throw new TypeError('Acceptance child environment cannot include credential variables');
  }
  const env = Object.fromEntries(
    Object.entries(sourceEnv).filter(([key]) => ACCEPTANCE_CHILD_ENV_KEYS.has(key.toLowerCase())),
  );
  return Object.assign(env, overrides);
}

/**
 * Build a public-install environment without inheriting credentials or user npm
 * configuration. Only PATH and the disposable managed root cross the boundary;
 * Windows process-launch variables are copied explicitly when required.
 */
export async function createPublicNpmEnvironment(managedRoot, {
  sourceEnv = process.env,
  platform = process.platform,
} = {}) {
  if (typeof managedRoot !== 'string' || managedRoot.length === 0) {
    throw new TypeError('A disposable managed root is required');
  }

  const directory = await mkdtemp(join(tmpdir(), 'qdrant-public-launcher-npm-'));
  const userConfig = join(directory, 'user.npmrc');
  const globalConfig = join(directory, 'global.npmrc');
  await writeFile(userConfig, '', { mode: 0o600 });
  await writeFile(globalConfig, '', { mode: 0o600 });

  const env = {
    PATH: sourceEnv.PATH ?? '',
    HOME: directory,
    USERPROFILE: directory,
    TMPDIR: directory,
    TEMP: directory,
    TMP: directory,
    QDRANT_MEMORY_MANAGED_ROOT: managedRoot,
    npm_config_userconfig: userConfig,
    npm_config_globalconfig: globalConfig,
    npm_config_cache: join(directory, 'cache'),
    npm_config_registry: PUBLIC_NPM_REGISTRY,
    npm_config_update_notifier: 'false',
    NO_UPDATE_NOTIFIER: '1',
  };

  if (platform === 'win32') {
    env.APPDATA = join(directory, 'AppData', 'Roaming');
    env.LOCALAPPDATA = join(directory, 'AppData', 'Local');
    await mkdir(env.APPDATA, { recursive: true });
    await mkdir(env.LOCALAPPDATA, { recursive: true });
    for (const key of ['SystemRoot', 'WINDIR', 'ComSpec', 'PATHEXT', 'SystemDrive']) {
      if (typeof sourceEnv[key] === 'string' && sourceEnv[key].length > 0) {
        env[key] = sourceEnv[key];
      }
    }
    const homeOnDrive = directory.match(/^([A-Za-z]:)(.*)$/);
    if (homeOnDrive) {
      env.HOMEDRIVE = homeOnDrive[1];
      env.HOMEPATH = homeOnDrive[2] || '\\';
    } else if (env.SystemDrive) {
      env.HOMEDRIVE = env.SystemDrive;
      env.HOMEPATH = directory;
    }
  }

  return {
    cwd: directory,
    env,
    cleanup: () => rm(directory, { recursive: true, force: true }),
  };
}
