/**
 * Exact public npm launcher acceptance.
 *
 * Runs the reviewed connector command and the reviewed DSH command through
 * `npx` with the exact pinned public package. No source checkout, no local
 * build, no system Python. Two modes:
 *
 *   node tests/public-launcher-acceptance.mjs --handshake-only
 *     Cold npx download, MCP initialize and tool discovery must finish
 *     within the connector timeout. Preparation starts in the background and
 *     is aborted by close; the probe must stay clean.
 *
 *   node tests/public-launcher-acceptance.mjs
 *     Full cold flow: preparation runs, CRUD and fresh-process persistence
 *     pass for both host profiles. The workbuddy phase resumes preparation
 *     that an aborted probe interrupted.
 *
 * The managed root must not traverse symlinks (the launcher rejects those),
 * so on macOS do not place it under /tmp or /var.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { existsSync } from 'node:fs';
import { readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

const handshakeOnly = process.argv.includes('--handshake-only');
const launcher = JSON.parse(await readFile(new URL('../launcher-source.json', import.meta.url), 'utf8'));
const spec = `${launcher.name}@${launcher.version}`;
const root = process.env.QDRANT_MEMORY_MANAGED_ROOT;
assert.ok(root, 'Set QDRANT_MEMORY_MANAGED_ROOT to a disposable managed root');
assert.ok(root.startsWith('/') || /^[A-Za-z]:[\\/]/.test(root), 'Managed root must be absolute');
const handshakeBudgetMs = 30000;
const start = performance.now();

// Node refuses to spawn .bat/.cmd files directly (CVE-2024-27980 fix). On
// Windows, run npm's npx CLI through the current node binary instead; that is
// exactly what the npx shim starts. Fall back to a quoted cmd.exe line.
function npxCommand(args) {
  if (process.platform !== 'win32') return { command: 'npx', args };
  const nodeRoot = dirname(process.execPath);
  const cli = [
    join(nodeRoot, 'node_modules', 'npm', 'bin', 'npx-cli.js'),
    join(nodeRoot, 'lib', 'node_modules', 'npm', 'bin', 'npx-cli.js'),
  ].find(candidate => existsSync(candidate));
  if (cli) return { command: process.execPath, args: [cli, ...args] };
  const line = ['npx', ...args].map(argument => `"${argument.replaceAll('"', '""')}"`).join(' ');
  return { command: process.env.ComSpec || 'cmd.exe', args: ['/d', '/s', '/c', line] };
}

function spawnNpx(args, options) {
  const resolved = npxCommand(args);
  return spawn(resolved.command, resolved.args, options);
}

function launch(host, extra = []) {
  const child = spawnNpx(['-y', spec, 'mcp', host, ...extra], {
    env: { ...process.env, QDRANT_MEMORY_MANAGED_ROOT: root },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const responses = new Map();
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => {
    let message;
    try { message = JSON.parse(line); }
    catch { throw new Error(`Launcher stdout is not protocol-only JSON: ${line.slice(0, 200)}`); }
    if (message.id !== undefined) responses.get(message.id)?.(message);
  });
  child.stderr.resume();
  let id = 0;
  async function request(method, params, timeoutMs = 30000) {
    const current = ++id;
    let timer;
    const response = new Promise((accept, reject) => {
      responses.set(current, accept);
      timer = setTimeout(() => reject(new Error(`Timed out waiting for ${method}`)), timeoutMs);
    });
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: current, method, params }) + '\n');
    try { return await response; } finally { clearTimeout(timer); responses.delete(current); }
  }
  async function initialize() {
    const response = await request('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'public-acceptance', version: '1' } }, handshakeBudgetMs);
    assert.equal(response.result?.serverInfo?.name, 'qdrant-memory-managed');
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
    return response;
  }
  async function tools() {
    const names = (await request('tools/list', {})).result.tools.map(tool => tool.name).sort();
    assert.deepEqual(names, ['qdrant_memory_add', 'qdrant_memory_delete', 'qdrant_memory_search', 'qdrant_memory_update']);
  }
  async function call(name, args) {
    const response = await request('tools/call', { name: 'qdrant_memory_' + name, arguments: args });
    assert.ok(!response.error, JSON.stringify(response.error));
    return response.result;
  }
  async function close() {
    child.stdin.end();
    await new Promise((accept, reject) => {
      const timer = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('Managed process did not unload')); }, 15000);
      child.once('close', code => { clearTimeout(timer); code === 0 ? accept() : reject(new Error(`Managed process failed with code ${code}`)); });
    });
  }
  return { child, request, initialize, tools, call, close };
}

async function waitReady(session, label) {
  const budget = Number(process.env.QDRANT_PUBLIC_ACCEPTANCE_WAIT_MS || 30 * 60 * 1000);
  const deadline = performance.now() + budget;
  for (;;) {
    const result = await session.call('search', { query: 'readiness' });
    if (!result.isError) return;
    const text = result.content[0].text;
    assert.ok(text.includes('Preparing'), `${label}: unexpected preparation failure: ${text}`);
    assert.ok(performance.now() < deadline, `${label}: preparation still running after ${Math.round(budget / 1000)}s: ${text}`);
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}

async function prepareDsh() {
  const prepare = spawnNpx(['-y', spec, 'prepare', 'dsh'], { env: { ...process.env, QDRANT_MEMORY_MANAGED_ROOT: root }, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let out = '';
  prepare.stdout.on('data', bytes => { out += bytes; });
  prepare.stderr.resume();
  await new Promise((accept, reject) => {
    const timer = setTimeout(() => { prepare.kill('SIGKILL'); reject(new Error('prepare dsh timed out')); }, 20 * 60 * 1000);
    prepare.once('close', code => { clearTimeout(timer); code === 0 ? accept() : reject(new Error(`prepare dsh failed with code ${code}`)); });
  });
  const last = out.trim().split('\n').at(-1);
  assert.equal(last, JSON.stringify({ ready: true, host: 'dsh' }), out);
}

const report = { passed: false, launcher: spec, handshake_budget_ms: handshakeBudgetMs, handshake_dsh_ms: null, handshake_workbuddy_ms: null, unprepared_probe_clean: false, workbuddy: false, dsh: false, no_write_replay: false, fresh_process_persistence: false, aborted_preparation_resumed: false };

async function writeReport() {
  const target = process.env.QDRANT_PUBLIC_ACCEPTANCE_REPORT;
  if (target) await writeFile(target, JSON.stringify(report, null, 2) + '\n');
}

// Phase A: an unprepared DSH probe must stay protocol-only and clean. It must
// not download, must not fake an installation and must refuse the write.
{
  const began = performance.now();
  const session = launch('dsh');
  await session.initialize();
  report.handshake_dsh_ms = Math.round(performance.now() - began);
  await session.tools();
  const attempted = await session.call('add', { text: 'Synthetic unprepared probe text' });
  assert.equal(attempted.isError, true, 'unprepared probe must not report success');
  assert.match(attempted.content[0].text, /preparation failed|Preparing|No operation/i);
  await session.close();
  const programRoot = join(root, 'programs');
  if (existsSync(programRoot)) {
    for (const entry of await readdir(programRoot)) {
      const files = await readdir(join(programRoot, entry));
      assert.ok(!files.includes('.provision.lock'), 'probe must not leave a provisioning lock');
      assert.ok(!files.includes('installed.json'), 'probe must not fake an installation');
    }
  }
  report.unprepared_probe_clean = true;
  console.log(JSON.stringify({ phase: 'unprepared-dsh-probe', clean: true, handshake_ms: report.handshake_dsh_ms }));
}

// Phase B: the exact connector command. The handshake must fit the connector
// timeout while preparation starts in the background. A pending write must be
// refused, never queued. Closing aborts the background preparation.
{
  const began = performance.now();
  const session = launch('workbuddy', ['--auto-setup']);
  await session.initialize();
  report.handshake_workbuddy_ms = Math.round(performance.now() - began);
  await session.tools();
  const pending = await session.call('add', { text: 'Synthetic queued write must never appear' });
  assert.equal(pending.isError, true, 'auto-setup add must not report success before readiness');
  await session.close();
  for (const [name, value] of Object.entries({ dsh: report.handshake_dsh_ms, workbuddy: report.handshake_workbuddy_ms })) {
    assert.ok(value < handshakeBudgetMs, `${name} handshake exceeded budget: ${value}ms`);
  }
  console.log(JSON.stringify({ phase: 'connector-command', handshake_ms: report.handshake_workbuddy_ms }));
  if (handshakeOnly) {
    report.passed = true;
    report.no_write_replay = true;
    await writeReport();
    console.log(JSON.stringify({ report }, null, 2));
    process.exit(0);
  }
}

// Phase C: the connector command resumes the preparation that the aborted
// probe interrupted, then serves real CRUD with fresh-process persistence.
{
  const session = launch('workbuddy', ['--auto-setup']);
  const began = performance.now();
  await session.initialize();
  await session.tools();
  await waitReady(session, 'workbuddy');
  report.aborted_preparation_resumed = true;
  const absent = await session.call('search', { query: 'Synthetic queued write must never appear' });
  assert.equal(JSON.parse(absent.content[0].text).memories.length, 0, 'a refused write must never execute later');
  const text = 'Synthetic public-launcher workbuddy preference';
  const created = JSON.parse((await session.call('add', { text })).content[0].text);
  await session.close();
  const second = launch('workbuddy');
  await second.initialize();
  await waitReady(second, 'workbuddy');
  const found = JSON.parse((await second.call('search', { query: text })).content[0].text);
  assert.ok(found.memories.some(m => m.id === created.id), 'fresh process must recall the saved memory');
  await second.call('update', { id: created.id, text: text + ' updated' });
  await second.close();
  const third = launch('workbuddy');
  await third.initialize();
  await waitReady(third, 'workbuddy');
  const updated = JSON.parse((await third.call('search', { query: text })).content[0].text);
  assert.ok(updated.memories.some(m => m.id === created.id && m.text.endsWith('updated')));
  await third.call('delete', { id: created.id });
  const gone = JSON.parse((await third.call('search', { query: text })).content[0].text);
  assert.ok(!gone.memories.some(m => m.id === created.id), 'deleted memory must disappear');
  await third.close();
  report.workbuddy = true;
  report.no_write_replay = true;
  report.fresh_process_persistence = true;
  console.log(JSON.stringify({ phase: 'workbuddy-resumed', handshake_ms: Math.round(performance.now() - began), persistence: true }));
}

// Phase D: DSH uses an explicit prepare step before the serving connection.
{
  await prepareDsh();
  const text = 'Synthetic public-launcher dsh preference';
  const first = launch('dsh');
  await first.initialize();
  await first.tools();
  await waitReady(first, 'dsh');
  const created = JSON.parse((await first.call('add', { text })).content[0].text);
  await first.close();
  const second = launch('dsh');
  await second.initialize();
  await waitReady(second, 'dsh');
  const found = JSON.parse((await second.call('search', { query: text })).content[0].text);
  assert.ok(found.memories.some(m => m.id === created.id));
  await second.call('delete', { id: created.id });
  await second.close();
  report.dsh = true;
  console.log(JSON.stringify({ phase: 'dsh', persistence: true }));
}

const workbuddyConfig = JSON.parse(await readFile(join(root, 'profiles', 'workbuddy', 'local', 'qdrant-memory.json'), 'utf8'));
const dshConfig = JSON.parse(await readFile(join(root, 'profiles', 'dsh', 'local', 'qdrant-memory.json'), 'utf8'));
assert.equal(workbuddyConfig.scope.agent_id, 'workbuddy');
assert.equal(dshConfig.scope.agent_id, 'dsh');

report.passed = true;
report.elapsed_seconds = Math.round((performance.now() - start) / 1000);
await writeReport();
console.log(JSON.stringify({ report }, null, 2));
if (process.env.QDRANT_PUBLIC_ACCEPTANCE_KEEP !== '1') {
  await rm(root, { recursive: true, force: true }).catch(() => {});
}
