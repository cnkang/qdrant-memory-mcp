import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PUBLIC_NPM_REGISTRY = 'https://registry.npmjs.org/';

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
    for (const key of ['SystemRoot', 'WINDIR', 'ComSpec', 'PATHEXT', 'SystemDrive']) {
      if (typeof sourceEnv[key] === 'string' && sourceEnv[key].length > 0) {
        env[key] = sourceEnv[key];
      }
    }
  }

  return {
    cwd: directory,
    env,
    cleanup: () => rm(directory, { recursive: true, force: true }),
  };
}
