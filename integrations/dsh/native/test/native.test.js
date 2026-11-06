import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DEFAULT_CONFIG,
  apply,
  compileTurn,
  formatMemories,
  parseCandidates,
} from '../index.js'

const candidate = {
  text: 'The DSH project uses the existing Python Runtime.',
  category: ['project'],
  importance: 0.8,
  replacement_intent: false,
}

test('automatic recall, capture, and injection default to disabled', () => {
  assert.equal(DEFAULT_CONFIG.auto_recall.enabled, false)
  assert.equal(DEFAULT_CONFIG.auto_capture.enabled, false)
  assert.equal(DEFAULT_CONFIG.memory_injection.enabled, false)
})

test('candidate parser accepts the Runtime schema and rejects extra or sensitive fields', () => {
  assert.deepEqual(parseCandidates(JSON.stringify({ memories: [candidate], replacement_context: '' })), {
    candidates: [candidate],
    replacement_context: '',
  })
  assert.deepEqual(parseCandidates(JSON.stringify({
    memories: [{ ...candidate, replacement_intent: true }],
    replacement_context: 'I am changing this preference.',
  }), 20, 'Yesterday I had one preference. I am changing this preference. Thank you.'), {
    candidates: [{ ...candidate, replacement_intent: true }],
    replacement_context: 'I am changing this preference.',
  })
  assert.throws(() => parseCandidates(JSON.stringify({
    memories: [{ ...candidate, replacement_intent: true }],
    replacement_context: 'invented replacement evidence',
  }), 20, 'No correction was stated.'))
  for (const memories of [
    [{ ...candidate, scope: { owner_id: 'forged' } }],
    [{ ...candidate, importance: true }],
    [{ ...candidate, text: 'token=super-secret-value-123456' }],
    Array.from({ length: 21 }, () => candidate),
  ]) {
    assert.throws(() => parseCandidates(JSON.stringify({ memories, replacement_context: '' })))
  }
  assert.throws(() => parseCandidates('```json\n{"memories":[]}\n```'))
})

test('turn projection excludes injected memory, tools, interrupted assistant text, and failed endings', () => {
  const events = [
    { type: 'turn/start', seq: 10, data: { turn: 4 } },
    { type: 'user/message', seq: 11, data: { role: 'user', source: { kind: 'qdrant-memory' }, content: [{ type: 'text', text: 'old context' }] } },
    { type: 'user/message', seq: 12, data: { role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'Remember that the DSH project uses Python.' }] } },
    { type: 'tool/result', seq: 13, data: { message: { content: [{ type: 'text', text: 'do not capture this' }] } } },
    { type: 'assistant/message', seq: 14, data: { turn: 4, interrupted: true, message: { source: { kind: 'model', provider: 'p', model: 'm' }, content: [{ type: 'text', text: 'unfinished answer' }] } } },
    { type: 'assistant/message', seq: 15, data: { turn: 4, message: { source: { kind: 'model', provider: 'p', model: 'm' }, content: [{ type: 'text', text: 'I will remember that.' }, { type: 'tool-call', name: 'ignore' }] } } },
    { type: 'turn/end', seq: 16, data: { turn: 4, reason: { kind: 'completed' } } },
  ]
  const turn = compileTurn(events, 'session-1', 4)
  assert.equal(turn.user, 'Remember that the DSH project uses Python.')
  assert.equal(turn.assistant, 'I will remember that.')
  assert.equal(turn.provider, 'p')
  assert.equal(turn.model, 'm')
  assert.equal(compileTurn(events, 'session-1', 5), null)
  assert.equal(compileTurn([
    events[0], events[2], events[5],
    { type: 'turn/end', seq: 16, data: { turn: 4, reason: { kind: 'max-tokens' } } },
  ], 'session-1', 4), null)
})

test('turn projection rejects credential-shaped data and oversized transcripts', () => {
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: { source: { kind: 'user' }, content: [{ type: 'text', text: 'my token=very-long-secret-value-123456' }] } },
    { type: 'assistant/message', seq: 3, data: { turn: 1, message: { source: { kind: 'model', provider: 'p', model: 'm' }, content: [{ type: 'text', text: 'ack' }] } } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  assert.equal(compileTurn(events, 'session-1', 1), null)
  assert.equal(compileTurn(events, 'session-1', 1, 8), null)
})

test('memory context is escaped, bounded, and omits credential-shaped records', () => {
  const result = formatMemories({ memories: [
    { id: 'memory-1', text: 'Treat <this> as historical data.' },
    { id: 'memory-2', text: 'api_key=private-secret-value-123456' },
  ] })
  assert.deepEqual(result.ids, ['memory-1'])
  assert.match(result.text, /\\u003cthis\\u003e/u)
  assert.match(result.text, /untrusted historical data/u)
  assert.equal(formatMemories({ memories: [{ id: 'x', text: 'long fact' }] }, 16).text, '')
})

test('recall options enforce score, result count, provenance and duplicate handling', () => {
  const result = formatMemories({ memories: [
    { id: 'low', text: 'low score', score: 0.1 },
    { id: 'memory-1', text: 'first copy', score: 0.8, source: 'shared_owner', category: ['preference'], created_at: '2026-11-06' },
    { id: 'memory-1', text: 'duplicate copy', score: 0.9 },
    { id: 'memory-2', text: 'second fact', score: 0.7 },
  ] }, 1000, {
    topK: 4,
    minScore: 0.5,
    dedupe: true,
    includeSourceMetadata: true,
  })
  assert.deepEqual(result.ids, ['memory-1', 'memory-2'])
  assert.match(result.text, /shared_owner/u)
  assert.match(result.text, /2026-11-06/u)
  assert.doesNotMatch(result.text, /duplicate copy/u)
})

test('opt-in recall enters the current pre-step decision once and keeps session cache isolated', async () => {
  const handlers = new Map()
  let cleanup
  const calls = []
  const config = {
    ...DEFAULT_CONFIG,
    auto_recall: { ...DEFAULT_CONFIG.auto_recall, enabled: true, cache: true },
    memory_injection: {
      ...DEFAULT_CONFIG.memory_injection,
      enabled: true,
      include_source_metadata: true,
    },
  }
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    agents: { get() { return undefined } },
  }
  const dispose = apply(ctx, config, async (mode, payload) => {
    calls.push({ mode, payload })
    return { memories: [{
      id: 'memory-1',
      score: 0.9,
      text: 'Use the existing Owner for DSH memory.',
      source: 'shared_owner',
      category: ['project'],
      created_at: '2026-11-06T00:00:00Z',
    }] }
  })
  const original = [{
    role: 'user',
    source: { kind: 'user' },
    content: [{ type: 'text', text: 'How should DSH access project memory?' }],
  }]
  const run = async (agent, turn) => {
    const decision = { kind: 'enter', messages: original }
    const result = await handlers.get('agent/pre-step')(
      { agent, messages: original, turn },
      async () => decision,
    )
    return { decision, result }
  }

  try {
    const firstAgent = { session: { id: 'profile-a-session' } }
    handlers.get('agent/created')({ agent: firstAgent })
    const first = await run(firstAgent, 1)
    assert.equal(first.result.messages.length, 2)
    assert.equal(first.result.messages[0], original[0])
    assert.equal(first.result.messages[1].source.kind, 'qdrant-memory')
    assert.deepEqual(first.result.messages[1].source.memoryIds, ['memory-1'])
    assert.match(first.result.messages[1].content[0].text, /shared_owner/u)
    assert.equal(first.decision.messages, original)
    assert.equal(calls.length, 1)

    const cached = await run(firstAgent, 2)
    assert.equal(cached.result.messages.length, 2)
    assert.equal(calls.length, 1)

    const otherAgent = { session: { id: 'profile-b-session' } }
    handlers.get('agent/created')({ agent: otherAgent })
    await run(otherAgent, 1)
    assert.equal(calls.length, 2)

    handlers.get('agent/disposed')({ agent: firstAgent })
    const resumedAgent = { session: { id: 'profile-a-session' } }
    handlers.get('agent/created')({ agent: resumedAgent })
    await run(resumedAgent, 3)
    assert.equal(calls.length, 3)
    assert.ok(calls.every((call) => call.mode === 'remote-call' && call.payload.query === 'How should DSH access project memory?'))
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

test('completed capture flushes the DSH log and retries from its stable Owner receipt', async () => {
  const session = { id: 'capture-session' }
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember that the project uses the existing Python Runtime.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'The project uses the existing Python Runtime.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  const snapshot = { events }
  const makeContext = (stream) => {
    const handlers = new Map()
    let cleanup
    const ctx = {
      on(event, handler) {
        handlers.set(event, handler)
        return () => handlers.delete(event)
      },
      effect(register) { cleanup = register() },
      logger: { warn() {} },
      llm: { stream },
      sessions: { async flush() { return true } },
      sessionQuery: { async readSession() { return snapshot } },
      agents: { get() { return undefined } },
    }
    return { ctx, handlers, getCleanup: () => cleanup }
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  let resolveSubmitted
  const submittedPromise = new Promise((resolve) => { resolveSubmitted = resolve })
  let extractionRequest
  const candidateOutput = JSON.stringify({
    memories: [{
      text: 'The project uses the existing Python Runtime.',
      category: ['project'],
      importance: 0.8,
      replacement_intent: false,
    }],
    replacement_context: '',
  })
  const firstContext = makeContext(async function* (request) {
    extractionRequest = request
    yield { type: 'text-delta', text: candidateOutput }
    yield { type: 'finish', reason: { kind: 'stop' } }
  })
  const firstRequests = []
  const firstAgent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const firstDispose = apply(firstContext.ctx, config, async (mode, payload, options) => {
    firstRequests.push({ mode, payload, options })
    if (options?.action === 'status') return { status: 'NOT_FOUND' }
    if (options?.action === 'submit') {
      resolveSubmitted(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  firstContext.handlers.get('agent/created')({ agent: firstAgent })
  firstContext.handlers.get('session/event')(session, {
    type: 'turn/end',
    data: { turn: 1, reason: { kind: 'completed' } },
  })

  let submitted
  let submitTimer
  try {
    submitted = await Promise.race([
      submittedPromise,
      new Promise((_, reject) => { submitTimer = setTimeout(() => reject(new Error('capture timed out')), 3000) }),
    ])
  } finally {
    clearTimeout(submitTimer)
    firstDispose()
  }
  assert.equal(submitted.candidate_schema, 'qdrant-memory/extraction-v1')
  assert.equal(submitted.session_id.startsWith('dsh-'), true)
  assert.equal(Object.hasOwn(submitted, 'user'), false)
  assert.equal(Object.hasOwn(submitted, 'assistant'), false)
  assert.equal(extractionRequest.purpose, 'qdrant-memory-extraction')
  assert.equal(extractionRequest.provider, 'provider-a')
  assert.match(extractionRequest.messages[0].content[0].text, /existing Python Runtime/u)
  assert.equal(firstRequests.filter((item) => item.options?.action === 'submit').length, 1)

  let recovered
  const recoveredPromise = new Promise((resolve) => { recovered = resolve })
  const replayContext = makeContext(async function* () {
    throw new Error('a committed receipt must not re-extract')
  })
  const replayAgent = { session, model: firstAgent.model }
  const replayDispose = apply(replayContext.ctx, config, async (_mode, payload, options) => {
    assert.equal(options.action, 'status')
    recovered(payload)
    return { status: 'COMMITTED' }
  })
  replayContext.handlers.get('agent/created')({ agent: replayAgent })
  let recoveryTimer
  try {
    const replay = await Promise.race([
      recoveredPromise,
      new Promise((_, reject) => { recoveryTimer = setTimeout(() => reject(new Error('recovery timed out')), 3000) }),
    ])
    assert.equal(replay.event_id, submitted.event_id)
  } finally {
    clearTimeout(recoveryTimer)
    replayDispose()
  }
})

test('disabled plugin hooks preserve the current pre-step decision', async () => {
  const handlers = new Map()
  let cleanup
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: { async *stream() { throw new Error('must not call model when disabled') } },
    sessions: { async flush() { throw new Error('must not flush when disabled') } },
    sessionQuery: { async readSession() { throw new Error('must not read when disabled') } },
    agents: { get() { return undefined } },
  }
  const dispose = apply(ctx, DEFAULT_CONFIG)
  const agent = { session: { id: 'session-1' } }
  const original = { kind: 'enter', messages: [] }
  const result = await handlers.get('agent/pre-step')(
    { agent, messages: [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'hello' }] }], turn: 1 },
    async () => original,
  )
  assert.equal(result, original)
  dispose()
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

test('Owner recall outage fails open without changing the current decision', async () => {
  const handlers = new Map()
  let cleanup
  let warningCount = 0
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() { warningCount += 1 } },
    agents: { get() { return undefined } },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_recall: { ...DEFAULT_CONFIG.auto_recall, enabled: true },
    memory_injection: { ...DEFAULT_CONFIG.memory_injection, enabled: true },
  }
  const agent = { session: { id: 'outage-session' } }
  const decision = { kind: 'enter', messages: [] }
  const dispose = apply(ctx, config, async () => { throw new Error('synthetic outage') })
  handlers.get('agent/created')({ agent })
  try {
    const result = await handlers.get('agent/pre-step')({
      agent,
      messages: [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'hello' }] }],
      turn: 1,
    }, async () => decision)
    assert.equal(result, decision)
    assert.equal(warningCount, 1)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})
