import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { createPublicNpmEnvironment } from './public-launcher-env.mjs';

test('public npm acceptance strips inherited credentials and npm configuration', async t => {
  const sandbox = await createPublicNpmEnvironment('/tmp/disposable-profile', {
    platform: 'linux',
    sourceEnv: {
      PATH: '/usr/bin',
      QDRANT_MEMORY_MANAGED_ROOT: '/real-profile',
      AWS_BEARER_TOKEN_BEDROCK: 'synthetic-secret-sentinel',
      OPENAI_API_KEY: 'synthetic-secret-sentinel',
      GITHUB_TOKEN: 'synthetic-secret-sentinel',
      NPM_TOKEN: 'synthetic-secret-sentinel',
      HTTPS_PROXY: 'https://user:synthetic-secret-sentinel@proxy.example',
      NODE_OPTIONS: '--require ./untrusted-hook.js',
      NPM_CONFIG_USERCONFIG: '/user/home/.npmrc',
      QDRANT_PUBLIC_ACCEPTANCE_REPORT: '/private/report.json',
    },
  });
  t.after(sandbox.cleanup);

  assert.deepEqual(Object.keys(sandbox.env).sort(), [
    'HOME', 'NO_UPDATE_NOTIFIER', 'PATH', 'QDRANT_MEMORY_MANAGED_ROOT',
    'TEMP', 'TMP', 'TMPDIR', 'USERPROFILE', 'npm_config_cache',
    'npm_config_globalconfig', 'npm_config_registry', 'npm_config_update_notifier',
    'npm_config_userconfig',
  ].sort());
  assert.equal(sandbox.env.QDRANT_MEMORY_MANAGED_ROOT, '/tmp/disposable-profile');
  assert.equal(sandbox.env.npm_config_registry, 'https://registry.npmjs.org/');
  assert.equal(sandbox.env.HOME, sandbox.cwd);
  assert.equal(await readFile(sandbox.env.npm_config_userconfig, 'utf8'), '');
  assert.equal(await readFile(sandbox.env.npm_config_globalconfig, 'utf8'), '');
});

test('Windows acceptance retains only required process-launch variables', async t => {
  const sandbox = await createPublicNpmEnvironment('C:\\temp\\disposable-profile', {
    platform: 'win32',
    sourceEnv: {
      PATH: 'C:\\Windows\\System32',
      SystemRoot: 'C:\\Windows',
      WINDIR: 'C:\\Windows',
      ComSpec: 'C:\\Windows\\System32\\cmd.exe',
      PATHEXT: '.COM;.EXE;.BAT;.CMD',
      SystemDrive: 'C:',
      AWS_BEARER_TOKEN_BEDROCK: 'synthetic-secret-sentinel',
      npm_config_registry: 'https://private.example/',
    },
  });
  t.after(sandbox.cleanup);

  assert.equal(sandbox.env.SystemRoot, 'C:\\Windows');
  assert.equal(sandbox.env.ComSpec, 'C:\\Windows\\System32\\cmd.exe');
  assert.equal(sandbox.env.AWS_BEARER_TOKEN_BEDROCK, undefined);
  assert.equal(sandbox.env.npm_config_registry, 'https://registry.npmjs.org/');
});

test('public acceptance routes every child through the isolated environment', async () => {
  const source = await readFile(new URL('./public-launcher-acceptance.mjs', import.meta.url), 'utf8');
  assert.equal((source.match(/\bspawn\s*\(/g) ?? []).length, 1);
  assert.match(source, /env:\s*npmEnvironment\.env/);
  assert.doesNotMatch(source, /\.\.\.process\.env|stderrDetail|line\.slice\(0,\s*200\)/);
});
