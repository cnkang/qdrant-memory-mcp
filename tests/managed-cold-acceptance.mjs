/** Explicit real-download gate; no system Python, uv or model service is used. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { locations, prepare, installed } from '../integrations/managed/provision.mjs';
const root = process.env.QDRANT_MEMORY_MANAGED_ROOT;
assert.ok(root, 'Choose an explicit disposable managed root');
const start = performance.now();
const dsh = locations('dsh'), wb = locations('workbuddy');
assert.notEqual(dsh.profile, wb.profile);
// Reproduce a host probe stopping after discovery while installation is partial.
// Then retry the same owned environment without deleting it or the user's data.
const interrupted = new AbortController();
await assert.rejects(prepare(dsh, 'dsh', interrupted.signal, stage => {
  if (stage === 'install-runtime') interrupted.abort();
}));
await assert.rejects(installed(dsh));
// A stopped probe can leave stale temporary files; the next preparation must
// replace them instead of failing on their presence.
await writeFile(join(dsh.program, process.platform === 'win32' ? 'uv.exe.pending' : 'uv.pending'), 'stale', { flag: 'w' });
await writeFile(join(dsh.program, 'runtime.tar.gz.pending'), 'stale', { flag: 'w' });
await prepare(dsh, 'dsh');
await prepare(wb, 'workbuddy');
const launcher = fileURLToPath(new URL('../integrations/managed/launcher.mjs', import.meta.url));

async function session(host, action) {
  const child = spawn(process.execPath, [launcher, 'mcp', host], { env: process.env, stdio: ['pipe', 'pipe', 'pipe'] });
  const responses = new Map();
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => {
    let message;
    try { message = JSON.parse(line); }
    catch { throw new Error(`Launcher stdout is not protocol-only JSON: ${line.slice(0, 200)}`); }
    responses.get(message.id)?.(message);
  });
  child.stderr.resume();
  let id = 0;
  async function request(method, params) {
    const current = ++id;
    let timer;
    const response = new Promise((accept, reject) => {
      responses.set(current, accept);
      timer = setTimeout(() => reject(new Error('Timed out waiting for managed MCP')), 30000);
    });
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: current, method, params }) + '\n');
    try { return await response; } finally { clearTimeout(timer); responses.delete(current); }
  }
  async function call(name, args) {
    const response = await request('tools/call', { name: 'qdrant_memory_' + name, arguments: args });
    assert.ok(!response.error);
    return response.result;
  }
  try {
    await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'cold-test', version: '1' } });
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
    assert.equal((await request('tools/list', {})).result.tools.length, 4);
    for (let count = 0; ; count++) {
      const result = await call('search', { query: 'readiness' });
      if (!result.isError) break;
      assert.ok(count < 120 && result.content[0].text.includes('Preparing'));
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    return await action(async (name, args) => {
      const result = await call(name, args);
      assert.equal(result.isError, false);
      return JSON.parse(result.content[0].text);
    });
  } finally {
    child.stdin.end();
    await new Promise((accept, reject) => {
      const timer = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('Managed process did not unload')); }, 10000);
      child.once('close', code => { clearTimeout(timer); code === 0 ? accept() : reject(new Error('Managed process failed')); });
    });
  }
}

for (const host of ['dsh', 'workbuddy']) {
  const text = `Synthetic ${host} cold-setup durable preference`;
  const id = await session(host, async call => (await call('add', { text })).id);
  await session(host, async call => {
    assert.ok((await call('search', { query: text })).memories.some(m => m.id === id));
    await call('update', { id, text: text + ' updated' });
  });
  await session(host, async call => {
    assert.ok((await call('search', { query: text })).memories.some(m => m.id === id && m.text.endsWith('updated')));
    await call('delete', { id });
    assert.ok(!(await call('search', { query: text })).memories.some(m => m.id === id));
  });
}
assert.equal(await installed(dsh), await installed(wb));
const cfg = JSON.parse(await readFile(wb.profile + '/qdrant-memory.json', 'utf8'));
assert.equal(cfg.scope.agent_id, 'workbuddy');
console.log(JSON.stringify({ passed: true, hosts: 2, interrupted_install_resumed: true, fresh_process_persistence: true, elapsed_seconds: Math.round((performance.now() - start) / 1000) }));
