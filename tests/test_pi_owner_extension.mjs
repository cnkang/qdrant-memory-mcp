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
