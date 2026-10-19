/** Real Pi 1.3 session hooks with a deterministic model; no paid model calls. */
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "../integrations/agent-hosts/node_modules/@earendil-works/pi-coding-agent/dist/index.js";
import { createAssistantMessageEventStream } from "../integrations/agent-hosts/node_modules/@earendil-works/pi-ai/dist/utils/event-stream.js";
import { createOwnerMemoryExtension, ownerRequest } from "../integrations/pi/owner-memory.mjs";

test("actual Pi session automatically captures and recalls without tool calls", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "qm-pi-host-"));
  const calls = [], contexts = [];
  const request = async (mode, value) => {
    calls.push({ mode, value });
    if (process.env.QM_REAL_OWNER === "1") return ownerRequest(mode, value);
    return mode === "remote-event" ? { status: "COMMITTED" } : {
      memories: [{ text: "Project Alpha uses SQLite WAL.", version: "v1", space_id: "alpha", created_by: "hermes-a" }],
    };
  };
  const modelRuntime = await ModelRuntime.create({ authPath: path.join(root, "auth.json"), modelsPath: null,
    modelsStorePath: path.join(root, "models.json"), refreshOnCreate: false, allowModelNetwork: false });
  modelRuntime.registerProvider("fixture", { api: "openai-completions", baseUrl: "http://127.0.0.1:1",
    apiKey: "synthetic-test-only", streamSimple: fixtureStream, models: [{ id: "fixture", name: "fixture", reasoning: false, input: ["text"],
      contextWindow: 32768, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }] });
  const settingsManager = SettingsManager.inMemory({});
  const loader = new DefaultResourceLoader({ cwd: root, agentDir: root, settingsManager,
    extensionFactories: [createOwnerMemoryExtension({ env: { QDRANT_MEMORY_AUTO_CAPTURE: "1", QDRANT_MEMORY_AUTO_RECALL: "1" }, request })] });
  await loader.reload();
  const { session } = await createAgentSession({ cwd: root, agentDir: root, resourceLoader: loader,
    modelRuntime, model: modelRuntime.getModel("fixture", "fixture"), settingsManager,
    sessionManager: SessionManager.inMemory(root), tools: [], thinkingLevel: "off" });
  function fixtureStream(model, context) {
    contexts.push(context);
    const stream = createAssistantMessageEventStream();
    const message = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
      content: [{ type: "text", text: JSON.stringify(context).includes("Project Alpha uses SQLite WAL") ? "SQLite WAL" : "unknown" }], stopReason: "stop", timestamp: Date.now(),
      usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
    queueMicrotask(() => { stream.push({ type: "done", reason: "stop", message }); stream.end(message); });
    return stream;
  }
  try {
    await session.prompt("Project Alpha journal mode?");
    assert.ok(contexts.length, JSON.stringify({ calls: calls.map(c => c.mode), messages: session.agent.state.messages.map(m => ({ role: m.role, reason: m.stopReason, error: m.errorMessage })) }));
    assert.ok(calls.some(call => call.mode === "remote-event"), "actual turn_end must capture");
    assert.ok(calls.some(call => call.mode === "remote-call"), "actual context hook must recall");
    assert.match(JSON.stringify(contexts), /Project Alpha uses SQLite WAL/);
    assert.equal(session.agent.state.messages.some(message => message.customType === "qdrant-owner-recall"), false,
      "shared recall must not persist in host transcript");
  } finally {
    session.dispose();
    await rm(root, { recursive: true, force: true });
  }
});
