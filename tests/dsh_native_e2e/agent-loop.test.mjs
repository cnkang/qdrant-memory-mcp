import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test, { after, before } from 'node:test'

const [nodeMajor, nodeMinor] = process.versions.node.split('.').map(Number)

before(() => {
  assert.ok(nodeMajor > 24 || (nodeMajor === 24 && nodeMinor >= 9), 'AgentLoop acceptance requires Node >=24.9.0')
})

// Resolve every Host service from the exact, locked official CLI installation.
const require = createRequire(new URL('../../.github/ci-deps/dsh-native/package.json', import.meta.url))
const load = async (name) => import(pathToFileURL(require.resolve(`@deepseek-ai/${name}`)))
const { Context } = await load('cordis')
const { default: LlmRuntime, LlmAdapter, createUserMessage } = await load('dsh-llm')
const { default: SessionStore, SessionId } = await load('dsh-session')
const { default: Projections } = await load('dsh-session-projection')
const { default: SystemPrompt } = await load('dsh-system-prompt')
const { default: ToolRuntime } = await load('dsh-tools')
const ToolExecutor = await load('dsh-tool-executor-native')
const { default: Agents } = await load('dsh-agent')
const { default: AgentLoop } = await load('dsh-agent-loop')
const Persistence = await load('dsh-session-persistence-jsonl')
const Query = await load('dsh-session-query')
const Boot = await load('dsh-app-boot')
const resolutionHome = await mkdtemp(join(tmpdir(), 'dsh-acceptance-resolution-'))
const resolutionContext = new Context()
const sourceProfile = process.env.QM_DSH_BUNDLE_PROFILE || join(resolutionHome, 'profiles/source')
const sourcePackage = fileURLToPath(new URL('../../integrations/dsh/native/', import.meta.url))
if (!process.env.QM_DSH_BUNDLE_PROFILE) {
  await mkdir(join(sourceProfile, 'node_modules/@cnkang'), { recursive: true })
  await symlink(sourcePackage, join(sourceProfile, 'node_modules/@cnkang/qdrant-memory-dsh-native'), process.platform === 'win32' ? 'junction' : 'dir')
  await writeFile(join(sourceProfile, 'package.json'), JSON.stringify({
  name: 'dsh-native-source-acceptance', private: true,
  dependencies: { '@cnkang/qdrant-memory-dsh-native': `file:${sourcePackage}` },
  dsh: { profile: { bundles: ['@cnkang/qdrant-memory-dsh-native'] } },
  }))
}
await resolutionContext.plugin(Boot.PluginPackages, { resolution: await Boot.createRuntimeResolution({
  installAnchor: require.resolve('@deepseek-ai/dsh/package.json'), home: resolutionHome,
  profile: Boot.loadProfileDirectory('dsh', sourceProfile, require.resolve('@deepseek-ai/dsh/package.json')),
}) })
after(async () => {
  await resolutionContext.fiber.dispose()
  await rm(resolutionHome, { recursive: true, force: true })
})
const Native = await import(process.env.QM_DSH_BUNDLE_PROFILE
  ? pathToFileURL(join(sourceProfile, 'node_modules/@cnkang/qdrant-memory-dsh-bundle/native/index.js'))
  : new URL('../../integrations/dsh/native/index.js', import.meta.url))

const fact = 'Synthetic Project Iris uses SQLite WAL.'
const captureFact = process.env.QM_DSH_CAPTURE_FACT || fact
const text = (value) => [
  { type: 'block-start', index: 0, blockType: 'text' },
  { type: 'text-delta', index: 0, text: value },
  { type: 'block-end', index: 0, block: { type: 'text', text: value } },
  { type: 'finish', reason: { kind: 'stop' } },
]

class DeterministicProvider extends LlmAdapter {
  requests = []
  failure = false
  hang = false
  toolOnce = false
  async resolveModel(provider, model) { return { provider, id: model, name: model } }
  async *stream(options) {
    if (this.failure) throw new Error('synthetic provider failure')
    if (this.hang) {
      yield { type: 'block-start', index: 0, blockType: 'text' }
      await new Promise((_, reject) => {
        if (options.signal.aborted) reject(new Error('cancelled'))
        else options.signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true })
      })
      return
    }
    const extraction = options.purpose === 'qdrant-memory-extraction'
    if (this.toolOnce && !extraction) {
      this.toolOnce = false
      yield* [
        { type: 'block-start', index: 0, blockType: 'tool-call' },
        { type: 'tool-call-delta', index: 0, id: 'synthetic-call', name: 'synthetic_missing_tool', argumentsDelta: '{}' },
        { type: 'block-end', index: 0, block: { type: 'tool-call', id: 'synthetic-call', name: 'synthetic_missing_tool', arguments: '{}' } },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ]
      return
    }
    const response = extraction ? JSON.stringify({ memories: [{
      text: captureFact, category: ['project'], importance: 0.8, replacement_intent: false,
    }], replacement_context: '' }) : 'Acknowledged synthetic fact.'
    yield* text(response)
  }
}

export async function until(predicate, label) {
  const deadline = Date.now() + (process.env.QM_DSH_CLOUD === '1' ? 90000 : 5000)
  while (!predicate()) {
    assert.ok(Date.now() < deadline, `Timed out: ${label}`)
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
}

export async function harness(t, config = {}, directory) {
  const root = directory || await mkdtemp(join(tmpdir(), 'dsh-real-loop-'))
  const ctx = new Context()
  t.after(async () => { await ctx.fiber.dispose(); if (!directory) await rm(root, { recursive: true, force: true }) })
  for (const plugin of [LlmRuntime, SessionStore, Projections, SystemPrompt, ToolRuntime, Agents]) {
    await ctx.plugin(plugin, plugin === SystemPrompt ? { personaPrefix: 'Synthetic system prompt: preserve exactly.' } : undefined)
  }
  await ctx.plugin(ToolExecutor)
  await ctx.plugin(Persistence, { root, compression: 'none' })
  // The query engine's concrete history methods are official; search is unused.
  await ctx.plugin(Query.default)
  await ctx.plugin(AgentLoop, { agents: [] })
  const provider = new DeterministicProvider()
  const cloud = process.env.QM_DSH_CLOUD === '1'
  const latency = []
  const usage = []
  ctx.on('llm/stream', (options, next) => {
    provider.requests.push(options)
    if (cloud && provider.requests.length > 4) throw new Error('Cloud acceptance per-process model-call budget exceeded')
    const start = Date.now()
    return (async function* () {
      try {
        for await (const chunk of next()) {
          if (chunk.type === 'usage') usage.push(chunk.usage)
          yield chunk
        }
      } finally { latency.push(Date.now() - start) }
    })()
  })
  if (cloud) {
    assert.equal(process.env.SOAK_LLM_BASE_URL, 'https://ollama.com/v1')
    assert.ok(process.env.SOAK_LLM_API_KEY, 'Cloud credential missing: NOT VERIFIED')
    assert.match(process.env.SOAK_LLM_MODEL || '', /^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,199}$/)
    await ctx.plugin(await load('dsh-llm-pi-ai'), { providers: { acceptance: {
      api: 'openai-completions', baseURL: 'https://ollama.com/v1', apiKeyEnv: 'SOAK_LLM_API_KEY',
      retryPolicy: { mode: 'normal', maxRetries: 0 },
      models: [{ id: process.env.SOAK_LLM_MODEL, contextWindow: 32768, maxTokens: 1200 }],
    } } })
  } else ctx.llm.registerAdapter(['acceptance'], provider)
  const receipts = []
  const calls = []
  const ownerState = { unavailable: false }
  const ownerLatency = []
  const runtime = async (mode, payload, options) => {
    calls.push({ mode, payload, action: options?.action })
    if (ownerState.unavailable) throw new Error('synthetic Owner outage')
    if (options?.action === 'status' && ownerState.statusBarrier) {
      const barrier = ownerState.statusBarrier
      ownerState.statusBarrier = null
      barrier.started()
      await barrier.promise
    }
    if (process.env.QM_DSH_REAL_OWNER === '1') {
      const start = performance.now()
      try {
        const result = await Native.runRuntimeRequest(mode, payload, options)
        if (options?.action === 'submit' && result.status === 'COMMITTED') receipts.push(payload)
        return result
      } finally { ownerLatency.push({ mode, action: options?.action, ms: performance.now() - start }) }
    }
    if (mode === 'remote-call') return { memories: [{ id: 'synthetic-memory-iris', text: fact, score: 1 }] }
    if (options.action === 'status') return { status: receipts.some((r) => r.event_id === payload.event_id) ? 'COMMITTED' : 'NOT_FOUND' }
    assert.equal(options.action, 'submit')
    receipts.push(payload)
    return { status: 'COMMITTED', event_id: payload.event_id }
  }
  let cleanup
  const mount = (settings = config) => ctx.plugin({
    name: 'qdrant-memory-acceptance', inject: Native.inject,
    apply(inner) { cleanup = Native.apply(inner, {
      auto_recall: { ...Native.DEFAULT_CONFIG.auto_recall, enabled: true },
      auto_capture: { ...Native.DEFAULT_CONFIG.auto_capture, enabled: true },
      memory_injection: { ...Native.DEFAULT_CONFIG.memory_injection, enabled: true },
      ...settings,
    }, runtime) },
  })
  const plugin = await mount()
  const create = (id) => ctx.agentLoop.create(SessionId(id), {
    provider: 'acceptance', model: cloud ? process.env.SOAK_LLM_MODEL : 'synthetic', maxTokens: 1200,
  })
  const send = async (agent, input, expected = 'completed') => {
    const done = new Promise((resolve) => {
      const off = ctx.on('agent/status', ({ agent: subject, status }) => {
        if (subject === agent && status === 'idle') { off(); resolve() }
      })
    })
    agent.followup(createUserMessage({ source: { kind: 'user' }, content: [{ type: 'text', text: input }] }))
    await Promise.race([done, new Promise((_, reject) => {
      const timer = setTimeout(() => reject(new Error('AgentLoop did not finish')), cloud ? 90000 : 5000)
      timer.unref()
    })])
    const end = agent.session.snapshotEvents().findLast((e) => e.type === 'turn/end')
    assert.equal(end?.data.reason.kind, expected, JSON.stringify(end))
  }
  return { ctx, provider, receipts, calls, ownerState, ownerLatency, create, send, plugin, mount, latency, usage, metrics: () => cleanup.metrics() }
}

test('complete DSH process restart resumes durable opt-in and uncaptured turns', { timeout: 30000 }, async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'dsh-process-recovery-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  for (const phase of ['prepare', 'resume']) {
    const env = { ...process.env, QM_DSH_PROCESS_PHASE: phase, QM_DSH_PROCESS_ROOT: directory }
    delete env.NODE_TEST_CONTEXT
    const child = spawnSync(process.execPath, ['--test', '--test-name-pattern=persisted process fixture',
      fileURLToPath(new URL('./process-fixture.mjs', import.meta.url))], {
      env,
      encoding: 'utf8', timeout: 12000,
    })
    assert.equal(child.status, 0, child.stdout + child.stderr)
    assert.match(child.stdout, /tests 1\b/, 'the child must actually execute its fixture')
  }
})

if (process.env.QM_DSH_BUNDLE_PROFILE) {
  test('packed Bundle runs Native and four MCP tools against one real Owner', { timeout: 30000 }, async (t) => {
    const h = await harness(t, Native.DEFAULT_CONFIG)
    await h.plugin.dispose()
    const Bundle = await import(pathToFileURL(join(sourceProfile, 'node_modules/@cnkang/qdrant-memory-dsh-bundle/index.js')))
    const bundle = await h.ctx.plugin(Bundle, {
      mode: 'unified-owner',
      auto_recall: { enabled: true }, auto_capture: { enabled: true }, memory_injection: { enabled: true },
    })
    const names = h.ctx.tools.definitions().map((tool) => tool.name).filter((name) => name.startsWith('mcp__qdrant-memory__'))
    assert.equal(names.length, 4)
    const agent = await h.create('iris-packed-bundle')
    await h.send(agent, captureFact)
    assert.ok(h.provider.requests.some((r) => JSON.stringify(r.messages).includes('Synthetic Project Iris')))
    let found
    const deadline = Date.now() + 10000
    do {
      const rows = await Native.runRuntimeRequest('remote-call', { query: 'Iris' })
      found = rows.memories.find((row) => row.text === captureFact)
      if (found) break
      await new Promise((resolve) => setTimeout(resolve, 50))
    } while (Date.now() < deadline)
    assert.ok(found, 'packed Native capture must reach the real Owner')
    await bundle.dispose()
    assert.equal(h.ctx.tools.definitions().filter((tool) => tool.name.startsWith('mcp__qdrant-memory__')).length, 0)
    const count = h.provider.requests.length
    await h.send(agent, 'Ordinary conversation after packed Bundle unload.')
    assert.equal(h.provider.requests.length, count + 1)
    assert.notEqual(h.provider.requests.at(-1).purpose, 'qdrant-memory-extraction')
    console.log(JSON.stringify({ bundle_model_calls: h.provider.requests.length,
      model_latency_ms: h.latency, usage: h.usage }))
  })
}

test('real AgentLoop injects recall into Provider requests and durable Session, then captures', { timeout: 180000 }, async (t) => {
  const h = await harness(t)
  const agent = await h.create('iris-real-loop')
  await h.send(agent, captureFact)
  await until(() => h.receipts.length === 1, 'completed capture')
  const request = h.provider.requests.find((r) => r.purpose !== 'qdrant-memory-extraction')
  const injected = request.messages.filter((m) => m.source?.kind === 'qdrant-memory')
  assert.equal(injected.length, 1)
  assert.match(JSON.stringify(injected), /Synthetic Project Iris/)
  assert.ok(injected[0].source.memoryIds.includes(process.env.QM_DSH_SEED_ID || 'synthetic-memory-iris'))
  assert.ok(!JSON.stringify(request.messages.filter((m) => m.role === 'system')).includes(fact))
  assert.match(JSON.stringify(request.messages.filter((m) => m.role === 'system')), /Synthetic system prompt: preserve exactly\./u)
  await h.ctx.sessions.flush(agent.session)
  const snapshot = await h.ctx.sessionQuery.readSession(agent.session.id)
  assert.ok(snapshot.events.some((e) => e.type === 'user/message' && e.data.source?.kind === 'qdrant-memory'))
  assert.equal(h.receipts[0].candidates[0].text, captureFact)
  assert.equal(h.metrics().recall_owner_calls, 1)
  assert.equal(h.metrics().capture_events_committed, 1)
  let activePlugin = h.plugin
  if (process.env.QM_DSH_CLOUD === '1') {
    await activePlugin.dispose()
    activePlugin = await h.mount({ auto_capture: Native.DEFAULT_CONFIG.auto_capture })
    const fresh = await h.create('iris-fresh-cloud-session')
    await h.send(fresh, 'Which synthetic Project Iris fact is in the supplied memory context?')
    const request = h.provider.requests.filter((r) => r.purpose !== 'qdrant-memory-extraction').at(-1)
    assert.match(JSON.stringify(request.messages), /Synthetic Project Iris/)
    console.log(JSON.stringify({ status: 'PASS', model: process.env.SOAK_LLM_MODEL,
      model_calls: h.provider.requests.length, latency_ms: h.latency, usage: h.usage,
      scope: 'synthetic-alice/project/iris', owner_receipt: 'COMMITTED' }))
  }
  await activePlugin.dispose()
  const callsBeforeDisabledTurn = h.provider.requests.length
  await h.send(agent, 'Ordinary conversation after plugin unload.')
  assert.equal(h.receipts.length, 1)
  assert.equal(h.provider.requests.length, callsBeforeDisabledTurn + 1)
  assert.notEqual(h.provider.requests.at(-1).purpose, 'qdrant-memory-extraction')
  if (process.env.QM_DSH_REAL_OWNER === '1') console.log(JSON.stringify({
    node: process.version, model_calls: h.provider.requests.length,
    owner_child_request_latency_ms: h.ownerLatency, model_latency_ms: h.latency,
    context_chars: h.metrics().injected_context_chars, usage: h.usage,
  }))
})

test('default-off automation makes no Owner or extraction calls', { timeout: 15000 }, async (t) => {
  const h = await harness(t, Native.DEFAULT_CONFIG)
  await h.send(await h.create('iris-disabled'), fact)
  assert.equal(h.calls.length, 0)
  assert.equal(h.provider.requests.length, 1)
})

test('failed real Provider turn is not captured', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  h.provider.failure = true
  await h.send(await h.create('iris-failure'), fact, 'error')
  assert.equal(h.provider.requests.length, 1)
  assert.equal(h.receipts.length, 0)
})

test('tool continuation does not recall twice in the same real turn', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  h.provider.toolOnce = true
  await h.send(await h.create('iris-tools'), captureFact)
  await until(() => h.receipts.length === 1, 'tool turn capture')
  assert.equal(h.provider.requests.filter((r) => r.purpose !== 'qdrant-memory-extraction').length, 2)
  assert.equal(h.metrics().recall_owner_calls, 1)
})

test('cancelled real turn never triggers extraction or capture', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  h.provider.hang = true
  const agent = await h.create('iris-cancel')
  const done = h.send(agent, captureFact, 'aborted')
  await until(() => h.provider.requests.length === 1, 'Provider request begins')
  agent.cancel({ kind: 'user' })
  await done
  assert.equal(h.receipts.length, 0)
  assert.equal(h.provider.requests.length, 1)
})

test('real delegated AgentLoop has no automatic memory authority', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  const handle = await h.ctx.agents.create({ sessionId: SessionId('iris-subagent'),
    meta: { origin: 'subagent', delegationDepth: 1 },
    agentOptions: { provider: 'acceptance', model: 'synthetic' },
  })
  await h.send(handle.agent, captureFact)
  assert.equal(h.calls.length, 0)
  assert.equal(h.provider.requests.length, 1)
  await handle.dispose()
})

test('real persisted AgentLoop resume retains receipts and captures only its next turn', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  const id = SessionId('iris-real-resume')
  const first = await h.ctx.agents.create({ sessionId: id, agentOptions: { provider: 'acceptance', model: 'synthetic' } })
  await h.send(first.agent, captureFact)
  await until(() => h.receipts.length === 1, 'initial receipt')
  await first.dispose()
  const resumed = await h.ctx.agents.resume({ resumeSessionId: id, agentOptions: { provider: 'acceptance', model: 'synthetic' } })
  await h.send(resumed.agent, captureFact)
  await until(() => h.receipts.length === 2, 'resumed new turn receipt')
  assert.equal(new Set(h.receipts.map((r) => r.event_id)).size, 2)
  await resumed.dispose()
})

test('real Agent takeover recovers an executing capture exactly once', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  const blocked = Promise.withResolvers()
  const release = Promise.withResolvers()
  t.after(() => release.resolve())
  h.ownerState.statusBarrier = { started: blocked.resolve, promise: release.promise }
  const id = SessionId('iris-executing-takeover')
  const first = await h.ctx.agents.create({ sessionId: id,
    agentOptions: { provider: 'acceptance', model: 'synthetic' },
  })
  await h.send(first.agent, captureFact)
  await blocked.promise
  await first.dispose()
  const replacement = await h.ctx.agents.resume({ resumeSessionId: id,
    agentOptions: { provider: 'acceptance', model: 'synthetic' },
  })
  release.resolve()
  await until(() => h.receipts.length === 1, 'takeover receipt')
  assert.equal(h.receipts[0].event_id, Native.compileTurn(replacement.agent.session.snapshotEvents(), id, 1).event_id)
  await h.send(replacement.agent, captureFact)
  await until(() => h.receipts.length === 2, 'replacement new turn receipt')
  assert.equal(new Set(h.receipts.map((r) => r.event_id)).size, 2)
  await replacement.dispose()
})

test('real fork excludes the inherited parent history from capture', { timeout: 15000 }, async (t) => {
  const h = await harness(t)
  const parent = await h.create('iris-real-parent')
  await h.send(parent, captureFact)
  await until(() => h.receipts.length === 1, 'parent receipt')
  const seed = parent.session.snapshotEvents()
  const child = await h.ctx.agents.create({ sessionId: SessionId('iris-real-child'), seed,
    inheritedEventCount: seed.length, meta: { parentSession: parent.session.id, isSeeded: true },
    agentOptions: { provider: 'acceptance', model: 'synthetic' },
  })
  await h.send(child.agent, captureFact)
  await until(() => h.receipts.length === 2, 'child new turn receipt')
  assert.equal(h.receipts[1].event_id, Native.compileTurn(child.agent.session.snapshotEvents(), child.agent.session.id, 2).event_id)
  await child.dispose()
})

test('first enable excludes existing history and HMR keeps the activation watermark', { timeout: 15000 }, async (t) => {
  const h = await harness(t, Native.DEFAULT_CONFIG)
  const agent = await h.create('iris-opt-in-history')
  await h.send(agent, 'Synthetic historical fact before consent.')
  await h.plugin.dispose()
  const enabled = await h.mount({})
  await h.send(agent, captureFact)
  await until(() => h.receipts.length === 1, 'new consented turn capture')
  assert.equal(h.receipts.length, 1)
  assert.equal(h.receipts[0].event_id, Native.compileTurn(agent.session.snapshotEvents(), agent.session.id, 2).event_id)
  await enabled.dispose()
  await h.mount({})
  await h.send(agent, captureFact)
  await until(() => h.receipts.length === 2, 'capture after HMR')
  assert.equal(new Set(h.receipts.map((r) => r.event_id)).size, 2)
})

for (const turns of [8, 16, 32, 100]) {
  test(`real AgentLoop captures ${turns} sequential turns without duplicate receipts`, { timeout: 30000 }, async (t) => {
    const h = await harness(t)
    const agent = await h.create(`iris-window-${turns}`)
    for (let index = 0; index < turns; index++) {
      await h.send(agent, captureFact)
      await until(() => h.receipts.length === index + 1, 'serial receipt')
    }
    assert.equal(new Set(h.receipts.map((r) => r.event_id)).size, turns)
  })
  test(`Owner outage and HMR recover ${turns} real completed turns in bounded batches`, { timeout: 30000 }, async (t) => {
    const h = await harness(t)
    h.ownerState.unavailable = true
    const agent = await h.create(`iris-outage-${turns}`)
    for (let index = 0; index < turns; index++) await h.send(agent, captureFact)
    await h.plugin.dispose()
    h.ownerState.unavailable = false
    await h.mount({})
    try {
      await until(() => h.receipts.length === turns, 'bounded history recovery')
    } catch {
      assert.fail(JSON.stringify({ receipts: h.receipts.length, metrics: h.metrics(),
        actions: h.calls.slice(-10).map((c) => c.action),
        markers: agent.session.snapshotEvents().filter((e) => e.type === 'plugin:qdrant-memory/capture-state'),
      }))
    }
    assert.equal(new Set(h.receipts.map((r) => r.event_id)).size, turns)
  })
}
