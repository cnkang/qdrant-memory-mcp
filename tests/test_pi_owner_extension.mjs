import assert from "node:assert/strict";
import test from "node:test";
import { createOwnerMemoryExtension } from "../integrations/pi/owner-memory.mjs";

test("default off does not register lifecycle capture", () => {
  createOwnerMemoryExtension({ env: {} })({ on() { assert.fail("Unexpected hook"); } });
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
