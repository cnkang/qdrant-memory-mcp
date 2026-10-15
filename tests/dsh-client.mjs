/** Actual official DSH MCP client over stdio; fixture registry is not the AgentLoop. */
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { readFile } from 'node:fs/promises';
const moduleRoot = process.env.DSH_TEST_MODULES;
if (!moduleRoot) throw new Error('Set DSH_TEST_MODULES to the installed node_modules directory');
const client = await import(pathToFileURL(join(moduleRoot, '@deepseek-ai/dsh-mcp-client/lib/index.js')));
const { Context } = await import(pathToFileURL(join(moduleRoot, '@deepseek-ai/cordis/lib/index.js')));
const { FileSystemSkillProvider } = await import(pathToFileURL(join(moduleRoot, '@deepseek-ai/dsh-skill-filesystem/lib/index.js')));
const config = JSON.parse(process.env.QDRANT_TEST_SERVER);
const namespace = 'mcp__qdrant-memory__qdrant_memory_';

async function connect() {
  const definitions = new Map();
  const ctx = new Context();
  ctx.provide('tools', { register(definition) {
    assert.ok(!definitions.has(definition.name));
    definitions.set(definition.name, definition);
    return () => definitions.delete(definition.name);
  } });
  const fiber = ctx.plugin(client, { serverName: 'qdrant-memory', transport: 'stdio', ...config,
    toolCallTimeoutMs: 10000, failOnStartupError: true });
  await fiber;
  assert.equal(definitions.size, 4);
  return { ctx, definitions, async close() { await fiber.dispose(); assert.equal(definitions.size, 0); },
    async call(name, args, signal = new AbortController().signal) {
      const definition = definitions.get(namespace + name);
      assert.ok(definition);
      const value = await definition.execute(args, { signal });
      const rendered = definition.output.render(args, value);
      assert.equal(rendered[0].type, 'text');
      return JSON.parse(rendered[0].text);
    } };
}

// DSH's temporary probe and the formal process are independent stdio clients.
const probe = await connect();
await probe.close();
const a = await connect();
let id;
try {
  const saved = await a.call('add', { text: 'DSH synthetic durable preference: use Python' });
  id = saved.id;
  assert.ok(id);
  const oldDefinition = a.definitions.get(namespace + 'search');
  const pid = Number(await readFile(process.env.QDRANT_TEST_PID, 'utf8'));
  process.kill(pid, 'SIGKILL');
  // Reconnect must finish before a new process reads the embedded profile.
  for (let attempt = 0; ; attempt++) {
    if (a.definitions.get(namespace + 'search') !== oldDefinition) break;
    assert.ok(attempt < 100, 'DSH failed to reconnect after child crash');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.ok((await a.call('search', { query: 'DSH synthetic durable preference' })).memories.some(m => m.id === id));
  const before = new AbortController(); before.abort();
  await assert.rejects(a.call('search', { query: 'cancelled' }, before.signal));
  await assert.rejects(a.call('update', { id: 'missing-id', text: 'denied' }));
} finally { await a.close(); }
// A fresh client has no Session A messages. Storage is its only source of recall.
const b = await connect();
try {
  const found = await b.call('search', { query: 'DSH synthetic durable preference: use Python' });
  assert.ok(found.memories.some(m => m.id === id));
  await b.call('update', { id, text: 'DSH synthetic durable preference: use Rust' });
} finally { await b.close(); }
const c = await connect();
try {
  const found = await c.call('search', { query: 'DSH synthetic durable preference: use Rust' });
  assert.ok(found.memories.some(m => m.id === id && m.text.includes('Rust')));
  await c.call('delete', { id });
  assert.ok(!(await c.call('search', { query: 'DSH synthetic durable preference' })).memories.some(m => m.id === id));
} finally { await c.close(); }

if (process.env.QDRANT_TEST_SKILL_ROOT) {
  const controller = new AbortController();
  const provider = new FileSystemSkillProvider({ get() { return undefined; }, logger: { warn() {}, debug() {} } },
    { signal: controller.signal, invalidate() {} },
    { includeDefaultRoots: false, customSkillDirs: [process.env.QDRANT_TEST_SKILL_ROOT], watch: false });
  try {
    const candidates = await provider.list({ cwd: process.cwd() });
    const candidate = candidates.find(x => x.name === 'qdrant-memory');
    assert.ok(candidate, 'Canonical Skill must be discovered');
    const skill = await provider.get(candidate, { signal: controller.signal });
    assert.ok(skill);
  } finally { controller.abort(); await provider.dispose(); }
}
console.log('DSH official client: probe/unload, crash/reconnect, four tools, rendering, errors, pre-cancel, CRUD and fresh-process persistence passed. AgentLoop/GUI/permissions require separate acceptance.');
