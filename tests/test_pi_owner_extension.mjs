import assert from "node:assert/strict";
import test from "node:test";
import { setImmediate } from "node:timers/promises";
import { createOwnerMemoryExtension } from "../integrations/pi/owner-memory.mjs";

function controlledOutbox(env) {
  const hooks = {}, entries = [], calls = [];
  let release, enter;
  const held = new Promise(resolve => { release = resolve; });
  const entered = new Promise(resolve => { enter = resolve; });
  const pi = { on(name, callback) { hooks[name] = callback; }, appendEntry(customType, data) { entries.push({ type: "custom", customType, data }); } };
  createOwnerMemoryExtension({ env, request: async (mode, value, configured) => {
    calls.push({ id: value.event_id, token: configured.QDRANT_MEMORY_REMOTE_TOKEN });
    if (calls.length === 1) enter();
    await held;
    return { status: "COMMITTED" };
  } })(pi);
  const ctx = { sessionManager: { getSessionId: () => "session", getEntries: () => entries }, hasUI: false };
  const turn = id => hooks.turn_end({ messageEntryId: id, message: { role: "assistant", content: [] } });
  return { hooks, entries, calls, release, entered, ctx, turn };
}

test("inflight recall cannot cross a changed read credential", async () => {
  const hooks = {};
  const env = { QDRANT_MEMORY_AUTO_RECALL: "1", QDRANT_MEMORY_RECALL_TOKEN: "a".repeat(40) };
  let release;
  const response = new Promise(resolve => { release = resolve; });
  createOwnerMemoryExtension({ env, request: async () => response })({ on(name, handler) { hooks[name] = handler; }, appendEntry() {} });
  await hooks.before_agent_start({ prompt: "original authorized project" }, { sessionManager: { getSessionId: () => "s" }, hasUI: false });
  const pending = hooks.context({ messages: [] });
  env.QDRANT_MEMORY_RECALL_TOKEN = "b".repeat(40);
  release({ memories: [{ text: "old project private result", version: "v1" }] });
  assert.deepEqual((await pending).messages, []);
});

test("pending delivery cannot block a prompt or duplicate sends during concurrent hooks", async () => {
  const h = controlledOutbox({ QDRANT_MEMORY_AUTO_CAPTURE: "1", QDRANT_MEMORY_REMOTE_TOKEN: "a".repeat(40) });
  await h.hooks.before_agent_start({ prompt: "first fact" }, h.ctx);
  const first = h.turn("one");
  await h.entered;
  let delivered = false;
  const prompt = h.hooks.before_agent_start({ prompt: "second fact" }, h.ctx).then(() => { delivered = true; });
  try {
    await setImmediate();
    assert.equal(delivered, true, "new prompt must not await the held outbox request");
    const second = h.turn("two");
    h.release();
    await Promise.all([first, second, prompt]);
    assert.deepEqual(h.calls.map(row => row.id), ["session:one", "session:two"]);
    assert.equal(h.entries.filter(row => row.customType === "qdrant-owner-ack").length, 2);
  } finally { h.release(); await Promise.allSettled([first, prompt]); }
});

test("a binding change during a drain cannot send old raw events using a new credential", async () => {
  const env = { QDRANT_MEMORY_AUTO_CAPTURE: "1", QDRANT_MEMORY_REMOTE_TOKEN: "a".repeat(40) };
  const h = controlledOutbox(env);
  await h.hooks.before_agent_start({ prompt: "old private fact" }, h.ctx);
  const first = h.turn("one");
  await h.entered;
  const oldPending = h.turn("two");
  env.QDRANT_MEMORY_REMOTE_TOKEN = "b".repeat(40);
  const next = h.hooks.before_agent_start({ prompt: "new authorized fact" }, h.ctx);
  const current = h.turn("three");
  h.release();
  await Promise.all([first, oldPending, next, current]);
  assert.deepEqual(h.calls, [
    { id: "session:one", token: "a".repeat(40) },
    { id: "session:three", token: "b".repeat(40) }
  ]);
  assert.deepEqual(h.entries.filter(row => row.customType === "qdrant-owner-ack").map(row => row.data.event_id), ["session:three"]);
});

test("default off does not register lifecycle capture", () => {
  createOwnerMemoryExtension({ env: {} })({ on() { assert.fail("Unexpected hook"); } });
});

test("Owner cancellation is terminal and is never reported as committed", async () => {
  const hooks = {}, entries = [];
  let sends = 0;
  const pi = { on(name, callback) { hooks[name] = callback; }, appendEntry(customType, data) { entries.push({ type: "custom", customType, data }); } };
  createOwnerMemoryExtension({ env: { QDRANT_MEMORY_AUTO_CAPTURE: "1" }, request: async () => { sends++; return { status: "CANCELLED" }; } })(pi);
  const ctx = { sessionManager: { getSessionId: () => "session", getEntries: () => entries }, hasUI: false };
  await hooks.session_start({}, ctx);
  await hooks.before_agent_start({ prompt: "synthetic permitted fact" }, ctx);
  await hooks.turn_end({ messageEntryId: "one", message: { role: "assistant", content: [] } });
  assert.equal(entries.at(-1).customType, "qdrant-owner-ack");
  assert.equal(entries.at(-1).data.status, "CANCELLED");
  await hooks.session_start({}, ctx);
  await hooks.session_shutdown();
  assert.equal(sends, 1);
});

test("official hook shapes retain failed events, retry IDs and fresh recall", async () => {
  const hooks = {}, entries = [], calls = [];
  let available = false;
  const pi = { on(name, callback) { hooks[name] = callback; }, appendEntry(customType, data) { entries.push({ type: "custom", customType, data }); } };
  const request = async (mode, value) => {
    calls.push({ mode, value });
    if (!available) throw new Error("synthetic outage");
    return mode === "remote-event" ? { status: "COMMITTED" } : { memories: [{ text: "SQLite WAL", version: "v1" }] };
  };
  createOwnerMemoryExtension({ env: { QDRANT_MEMORY_AUTO_CAPTURE: "1", QDRANT_MEMORY_AUTO_RECALL: "1" }, request })(pi);
  const ctx = { sessionManager: { getSessionId: () => "session", getEntries: () => entries }, hasUI: false };
  await hooks.session_start({}, ctx);
  await hooks.before_agent_start({ prompt: "Project Alpha uses SQLite WAL." }, ctx);
  await hooks.turn_end({ messageEntryId: "turn1", message: { role: "assistant", content: [{ type: "text", text: "ack" }] } });
  assert.equal(entries.filter(e => e.customType === "qdrant-owner-event").length, 1);
  available = true;
  await hooks.session_start({}, ctx);
  assert.equal(entries.at(-1).customType, "qdrant-owner-ack");
  const sends = calls.filter(c => c.mode === "remote-event");
  assert.equal(sends[0].value.event_id, sends[1].value.event_id);
  assert.equal(await hooks.before_agent_start({ prompt: "journal mode?" }, ctx), undefined);
  const result = await hooks.context({ messages: [{ role: "user", content: "question" }] }, ctx);
  assert.match(result.messages.at(-1).content, /SQLite WAL/);
  available = false;
  const denied = await hooks.context({ messages: result.messages }, ctx);
  assert.equal(denied.messages.length, 1);
});

test("pending events cannot be replayed after a credential or Owner binding change", async () => {
  const hooks = {}, entries = [], sends = [];
  const env = { QDRANT_MEMORY_AUTO_CAPTURE: "1", QDRANT_MEMORY_OWNER_URL: "https://owner.test/mcp", QDRANT_MEMORY_REMOTE_TOKEN: "a".repeat(40) };
  let online = false;
  const pi = { on(name, callback) { hooks[name] = callback; }, appendEntry(customType, data) { entries.push({ type: "custom", customType, data }); } };
  createOwnerMemoryExtension({ env, request: async (mode, value) => { sends.push(value); if (online) return { status: "COMMITTED" }; throw new Error("offline"); } })(pi);
  const ctx = { sessionManager: { getSessionId: () => "session", getEntries: () => entries }, hasUI: false };
  await hooks.session_start({}, ctx);
  await hooks.before_agent_start({ prompt: "private original project" }, ctx);
  await hooks.turn_end({ messageEntryId: "turn1", message: { role: "assistant", content: [] } });
  env.QDRANT_MEMORY_REMOTE_TOKEN = "b".repeat(40);
  await hooks.before_agent_start({ prompt: "new project" }, ctx);
  assert.equal(sends.length, 1);
  online = true;
  await hooks.turn_end({ messageEntryId: "turn2", message: { role: "assistant", content: [] } });
  assert.equal(sends.length, 2);
  assert.equal(sends[1].user, "new project");
});

test("ephemeral recall bounds long text while keeping complete provenance", async () => {
  const hooks = {};
  const pi = { on(name, callback) { hooks[name] = callback; }, appendEntry() {} };
  createOwnerMemoryExtension({ env: { QDRANT_MEMORY_AUTO_RECALL: "1" }, request: async () => ({ memories: [
    { text: "x".repeat(10000), space_id: "alpha", version: "v1", created_by: "hermes-a", id: "one" }
  ] }) })(pi);
  await hooks.before_agent_start({ prompt: "Alpha?" }, { sessionManager: { getSessionId: () => "s" }, hasUI: false });
  const result = await hooks.context({ messages: [] });
  const content = result.messages[0].content;
  assert.ok(content.length <= 4100);
  const rows = JSON.parse(content.split("\n").at(-1));
  assert.equal(rows[0].version, "v1");
  assert.equal(rows[0].space_id, "alpha");
  assert.equal(rows[0].created_by, "hermes-a");
});

test("private capture and project recall use independently scoped credentials", async () => {
  const hooks = {}, calls = [];
  const env = { QDRANT_MEMORY_AUTO_CAPTURE: "1", QDRANT_MEMORY_AUTO_RECALL: "1",
    QDRANT_MEMORY_REMOTE_TOKEN: "private-device-token", QDRANT_MEMORY_RECALL_TOKEN: "project-read-token" };
  const pi = { on(name, callback) { hooks[name] = callback; }, appendEntry() {} };
  createOwnerMemoryExtension({ env, request: async (mode, value, configured) => {
    calls.push({ mode, token: configured.QDRANT_MEMORY_REMOTE_TOKEN });
    return mode === "remote-call" ? { memories: [] } : { status: "COMMITTED" };
  } })(pi);
  await hooks.before_agent_start({ prompt: "Project Alpha?" }, { sessionManager: { getSessionId: () => "s" }, hasUI: false });
  await hooks.context({ messages: [] });
  await hooks.turn_end({ messageEntryId: "one", message: { role: "assistant", content: [] } });
  assert.equal(calls.find(call => call.mode === "remote-call").token, "project-read-token");
  assert.equal(calls.find(call => call.mode === "remote-event").token, "private-device-token");
});
