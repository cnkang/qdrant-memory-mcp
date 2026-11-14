#!/usr/bin/env node
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { realpath } from 'node:fs/promises';
import { bridge } from './bridge.mjs';
import { locations, installed, prepare } from './provision.mjs';

export async function main(args) {
  const [mode, host, ...rest] = args;
  if (!['prepare', 'mcp'].includes(mode) || !host || rest.some(x => x !== '--auto-setup')
      || (rest.length && (mode !== 'mcp' || host !== 'workbuddy')) || rest.length > 1) {
    throw new Error('Usage: launcher.mjs prepare|mcp workbuddy|dsh [--auto-setup (WorkBuddy only)]');
  }
  const paths = locations(host);
  if (mode === 'prepare') {
    const controller = new AbortController();
    const stop = () => controller.abort();
    process.once('SIGTERM', stop);
    process.once('SIGINT', stop);
    try { await prepare(paths, host, controller.signal); }
    finally { process.removeListener('SIGTERM', stop); process.removeListener('SIGINT', stop); }
    console.log(JSON.stringify({ ready: true, host }));
  } else {
    await bridge(async signal => ({
      command: rest.includes('--auto-setup') ? await prepare(paths, host, signal) : await installed(paths),
      args: ['--home', paths.profile, 'mcp'],
      env: { ...process.env, PYTHONNOUSERSITE: '1', PYTHONPATH: '', PYTHONHOME: '' },
    }));
  }
}

export function sameEntryPath(left, right, platform = process.platform) {
  const pathApi = platform === 'win32' ? path.win32 : path.posix;
  const normalizedLeft = pathApi.resolve(left);
  const normalizedRight = pathApi.resolve(right);
  return platform === 'win32'
    ? normalizedLeft.toLowerCase() === normalizedRight.toLowerCase()
    : normalizedLeft === normalizedRight;
}

async function isCurrentEntrypoint(argumentPath, moduleUrl) {
  const [argumentRealPath, moduleRealPath] = await Promise.all([
    realpath(argumentPath),
    realpath(fileURLToPath(moduleUrl)),
  ]);
  return sameEntryPath(argumentRealPath, moduleRealPath);
}

if (process.argv[1] && await isCurrentEntrypoint(process.argv[1], import.meta.url)) {
  try { await main(process.argv.slice(2)); }
  catch (error) {
    // Keep the message bounded: only the internal stage label may be added.
    const stage = error && typeof error.stage === 'string' && /^[a-z][a-z-]*$/.test(error.stage) ? ` Failed stage: ${error.stage}.` : '';
    console.error(`Qdrant Memory launcher failed. Check command, preparation, network, disk space and profile ownership. No profile was reset.${stage}`);
    process.exitCode = 1;
  }
}
