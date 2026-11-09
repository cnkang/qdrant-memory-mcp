import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { delimiter, resolve } from 'node:path'
import { PassThrough } from 'node:stream'
import test from 'node:test'
import {
  Config,
  DEFAULT_CONFIG,
  RUNTIME_BOOTSTRAP,
  apply,
  compileTurn,
  formatMemories,
  parseCandidates,
  runRuntimeRequest,
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
  assert.equal(Config['~standard'].validate(DEFAULT_CONFIG).issues, undefined)
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

test('runtime launcher reports an unsuccessful local Runtime process', async () => {
  const runtimeEnvironment = {
    QDRANT_MEMORY_RUNTIME_PYTHON: process.execPath,
    QDRANT_MEMORY_DSH_OWNER_URL: 'https://owner.example/mcp',
    QDRANT_MEMORY_DSH_OWNER_TOKEN: 't'.repeat(32),
    QDRANT_MEMORY_RUNTIME_CA_FILE: process.execPath,
  }
  const previousEnvironment = Object.fromEntries(
    Object.keys(runtimeEnvironment).map((key) => [key, process.env[key]]),
  )
  Object.assign(process.env, runtimeEnvironment)
  try {
    await assert.rejects(
      runRuntimeRequest('remote-call', { probe: true }, { timeoutMs: 1000 }),
      /Owner Runtime request failed/u,
    )
  } finally {
    for (const [key, value] of Object.entries(previousEnvironment)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})

test('runtime launcher rejects a prefixed Owner endpoint path', async () => {
  const runtimeEnvironment = {
    QDRANT_MEMORY_RUNTIME_PYTHON: process.execPath,
    QDRANT_MEMORY_DSH_OWNER_URL: 'https://owner.example/prefix/mcp',
    QDRANT_MEMORY_DSH_OWNER_TOKEN: 't'.repeat(32),
    QDRANT_MEMORY_RUNTIME_CA_FILE: process.execPath,
  }
  const previousEnvironment = Object.fromEntries(
    Object.keys(runtimeEnvironment).map((key) => [key, process.env[key]]),
  )
  Object.assign(process.env, runtimeEnvironment)
  try {
    assert.throws(
      () => runRuntimeRequest('remote-call', { query: 'x' }, { timeoutMs: 1000 }),
      /HTTPS \/mcp/u,
    )
  } finally {
    for (const [key, value] of Object.entries(previousEnvironment)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})

test('runtime launcher round-trips remote calls and events through a stub process', async () => {
  const runtimeEnvironment = {
    QDRANT_MEMORY_RUNTIME_PYTHON: '/private/runtime/bin/python',
    QDRANT_MEMORY_DSH_OWNER_URL: 'https://owner.example/mcp',
    QDRANT_MEMORY_DSH_OWNER_TOKEN: 't'.repeat(32),
    QDRANT_MEMORY_RUNTIME_CA_FILE: process.execPath,
  }
  const previousEnvironment = Object.fromEntries(
    Object.keys(runtimeEnvironment).map((key) => [key, process.env[key]]),
  )
  Object.assign(process.env, runtimeEnvironment)
  const stubSpawn = (response) => {
    const calls = []
    const spawnProcess = (command, args, options) => {
      const child = new EventEmitter()
      child.stdout = new PassThrough()
      child.stdin = new PassThrough()
      const call = { command, args, options, stdin: '' }
      const chunks = []
      child.stdin.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
      child.stdin.on('finish', () => {
        call.stdin = Buffer.concat(chunks).toString('utf8')
        child.stdout.end(JSON.stringify(response))
        setImmediate(() => child.emit('close', 0))
      })
      calls.push(call)
      return child
    }
    return { calls, spawnProcess }
  }

  try {
    const query = { query: 'project memory' }
    const callStub = stubSpawn({ memories: [{ id: 'm1', text: 'A fact.' }] })
    const callResult = await runRuntimeRequest('remote-call', query, {
      spawnProcess: callStub.spawnProcess,
    })
    assert.deepEqual(callResult, { memories: [{ id: 'm1', text: 'A fact.' }] })
    assert.equal(callStub.calls[0].command, runtimeEnvironment.QDRANT_MEMORY_RUNTIME_PYTHON)
    assert.deepEqual(callStub.calls[0].args, [
      '-I', '-S', '-X', 'utf8', '-c', RUNTIME_BOOTSTRAP, 'remote-call',
      '--url', runtimeEnvironment.QDRANT_MEMORY_DSH_OWNER_URL,
      '--token-env', 'QDRANT_MEMORY_DSH_OWNER_TOKEN',
      '--ca-file', process.execPath,
      '--tool', 'qdrant_memory_search',
    ])
    assert.equal(callStub.calls[0].options.cwd, '/private/runtime/bin')
    assert.equal(callStub.calls[0].stdin, JSON.stringify(query))

    const event = { event_id: 'event-1' }
    const eventStub = stubSpawn({ event_id: 'event-1', status: 'COMMITTED' })
    const eventResult = await runRuntimeRequest('remote-event', event, {
      action: 'retry',
      spawnProcess: eventStub.spawnProcess,
    })
    assert.deepEqual(eventResult, { event_id: 'event-1', status: 'COMMITTED' })
    assert.deepEqual(eventStub.calls[0].args, [
      '-I', '-S', '-X', 'utf8', '-c', RUNTIME_BOOTSTRAP, 'remote-event',
      '--url', runtimeEnvironment.QDRANT_MEMORY_DSH_OWNER_URL,
      '--token-env', 'QDRANT_MEMORY_DSH_OWNER_TOKEN',
      '--ca-file', process.execPath,
      '--action', 'retry',
    ])
    assert.equal(eventStub.calls[0].options.cwd, '/private/runtime/bin')
    assert.equal(eventStub.calls[0].stdin, JSON.stringify(event))
  } finally {
    for (const [key, value] of Object.entries(previousEnvironment)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})

test('runtime launcher resolves a relative inherited CA file before changing directories', async () => {
  const runtimeEnvironment = {
    QDRANT_MEMORY_RUNTIME_PYTHON: '/private/runtime/bin/python',
    QDRANT_MEMORY_DSH_OWNER_URL: 'https://owner.example/mcp',
    QDRANT_MEMORY_DSH_OWNER_TOKEN: 't'.repeat(32),
    QDRANT_MEMORY_RUNTIME_CA_FILE: process.execPath,
    SSL_CERT_FILE: 'certs/owner-ca.pem',
  }
  const previousEnvironment = Object.fromEntries(
    Object.keys(runtimeEnvironment).map((key) => [key, process.env[key]]),
  )
  Object.assign(process.env, runtimeEnvironment)
  const calls = []
  const spawnProcess = (command, args, options) => {
    const child = new EventEmitter()
    child.stdout = new PassThrough()
    child.stdin = new PassThrough()
    calls.push({ command, args, options })
    child.stdin.on('data', () => {})
    child.stdin.on('finish', () => {
      child.stdout.end(JSON.stringify({ memories: [] }))
      setImmediate(() => child.emit('close', 0))
    })
    return child
  }

  try {
    await runRuntimeRequest('remote-call', { query: 'one' }, { spawnProcess })
    assert.equal(calls[0].options.env.SSL_CERT_FILE, resolve(process.cwd(), 'certs/owner-ca.pem'))

    process.env.SSL_CERT_FILE = process.execPath
    await runRuntimeRequest('remote-call', { query: 'two' }, { spawnProcess })
    assert.equal(calls[1].options.env.SSL_CERT_FILE, process.execPath)

    delete process.env.SSL_CERT_FILE
    await runRuntimeRequest('remote-call', { query: 'three' }, { spawnProcess })
    assert.equal('SSL_CERT_FILE' in calls[2].options.env, false)

    process.env.SSL_CERT_FILE = ''
    await runRuntimeRequest('remote-call', { query: 'four' }, { spawnProcess })
    assert.equal(calls[3].options.env.SSL_CERT_FILE, '')
  } finally {
    for (const [key, value] of Object.entries(previousEnvironment)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})

test('runtime launcher resolves relative inherited CA directories before changing directories', async () => {
  const runtimeEnvironment = {
    QDRANT_MEMORY_RUNTIME_PYTHON: '/private/runtime/bin/python',
    QDRANT_MEMORY_DSH_OWNER_URL: 'https://owner.example/mcp',
    QDRANT_MEMORY_DSH_OWNER_TOKEN: 't'.repeat(32),
    QDRANT_MEMORY_RUNTIME_CA_FILE: process.execPath,
    SSL_CERT_DIR: ['certs', 'shared/certs'].join(delimiter),
  }
  const previousEnvironment = Object.fromEntries(
    Object.keys(runtimeEnvironment).map((key) => [key, process.env[key]]),
  )
  Object.assign(process.env, runtimeEnvironment)
  const calls = []
  const spawnProcess = (command, args, options) => {
    const child = new EventEmitter()
    child.stdout = new PassThrough()
    child.stdin = new PassThrough()
    calls.push({ command, args, options })
    child.stdin.on('data', () => {})
    child.stdin.on('finish', () => {
      child.stdout.end(JSON.stringify({ memories: [] }))
      setImmediate(() => child.emit('close', 0))
    })
    return child
  }

  try {
    await runRuntimeRequest('remote-call', { query: 'one' }, { spawnProcess })
    assert.equal(
      calls[0].options.env.SSL_CERT_DIR,
      [resolve(process.cwd(), 'certs'), resolve(process.cwd(), 'shared/certs')].join(delimiter),
    )

    process.env.SSL_CERT_DIR = ['/absolute/ca', 'relative/ca', ''].join(delimiter)
    await runRuntimeRequest('remote-call', { query: 'two' }, { spawnProcess })
    assert.equal(
      calls[1].options.env.SSL_CERT_DIR,
      ['/absolute/ca', resolve(process.cwd(), 'relative/ca'), ''].join(delimiter),
    )

    delete process.env.SSL_CERT_DIR
    await runRuntimeRequest('remote-call', { query: 'three' }, { spawnProcess })
    assert.equal('SSL_CERT_DIR' in calls[2].options.env, false)
  } finally {
    for (const [key, value] of Object.entries(previousEnvironment)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
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

test('turn projection rejects credentials and applies the input size limit independently', () => {
  const credentialEvents = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: { source: { kind: 'user' }, content: [{ type: 'text', text: 'my token=very-long-secret-value-123456' }] } },
    { type: 'assistant/message', seq: 3, data: { turn: 1, message: { source: { kind: 'model', provider: 'p', model: 'm' }, content: [{ type: 'text', text: 'ack' }] } } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  assert.equal(compileTurn(credentialEvents, 'session-1', 1), null)

  const sizeEvents = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: { source: { kind: 'user' }, content: [{ type: 'text', text: 'Remember the project setting.' }] } },
    { type: 'assistant/message', seq: 3, data: { turn: 1, message: { source: { kind: 'model', provider: 'p', model: 'm' }, content: [{ type: 'text', text: 'Understood.' }] } } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  assert.ok(compileTurn(sizeEvents, 'session-1', 1))
  assert.equal(compileTurn(sizeEvents, 'session-1', 1, 16), null)
})

test('memory context is escaped, bounded, and omits credential-shaped records', () => {
  const result = formatMemories({ memories: [
    { id: 'memory-1', text: 'Treat <this> as historical data.' },
    { id: 'memory-2', text: 'api_key=private-secret-value-123456' },
  ] })
  assert.deepEqual(result.ids, ['memory-1'])
  assert.match(result.text, /\\u003cthis\\u003e/u)
  assert.match(result.text, /untrusted historical data/u)
  assert.equal(result.chars, result.text.length)
  assert.deepEqual(formatMemories(null), { text: '', ids: [], chars: 0 })
  assert.deepEqual(formatMemories({ memories: null }), { text: '', ids: [], chars: 0 })
  assert.equal(formatMemories({ memories: [{ id: 'x', text: 'long fact' }] }, 16).text, '')
  const small = { id: 'small', text: 'ok' }
  const expectedSmall = formatMemories({ memories: [small] })
  const afterOversized = formatMemories({
    memories: [{ id: 'large', text: 'x'.repeat(200) }, small],
  }, expectedSmall.text.length)
  assert.deepEqual(afterOversized, expectedSmall)
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
  const run = async (agent, turn, messages = original) => {
    const decision = { kind: 'enter', messages }
    const result = await handlers.get('agent/pre-step')(
      { agent, messages, turn },
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

    const credentialMessages = [{
      role: 'user',
      source: { kind: 'user' },
      content: [{ type: 'text', text: '{"api_key":"private-secret-value-123456"}' }],
    }]
    const skippedCredential = await run(firstAgent, 4, credentialMessages)
    assert.equal(skippedCredential.result, skippedCredential.decision)
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
  const metrics = dispose.metrics()
  assert.equal(metrics.recall_requests, 4)
  assert.equal(metrics.recall_owner_calls, 3)
  assert.equal(metrics.recall_cache_hits, 1)
  assert.equal(metrics.recall_hits, 4)
  assert.equal(metrics.injected_memory_count, 4)
  assert.equal(metrics.recall_latency_ms_count, 3)
  assert.ok(metrics.injected_context_chars > 0)
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
  const makeContext = (stream, {
    agents = { get() { return undefined }, list() { return [] } },
    flush = async () => true,
    readSession = async () => snapshot,
  } = {}) => {
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
      sessions: { flush },
      sessionQuery: { readSession },
      agents,
    }
    return { ctx, handlers, getCleanup: () => cleanup }
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  let resolveSubmitted
  const submittedPromise = new Promise((resolve) => { resolveSubmitted = resolve })
  let releaseFirstFlush
  const firstFlush = new Promise((resolve) => { releaseFirstFlush = resolve })
  let firstFlushCalls = 0
  let firstReadCalls = 0
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
  }, {
    flush() {
      firstFlushCalls += 1
      return firstFlush
    },
    async readSession() {
      firstReadCalls += 1
      return snapshot
    },
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
  const captureCompletion = firstContext.handlers.get('session/event')(session, {
    type: 'turn/end',
    data: { turn: 1, reason: { kind: 'completed' } },
  })

  let submitted
  let submitTimer
  try {
    assert.equal(typeof captureCompletion?.then, 'function')
    assert.ok(firstFlushCalls > 0)
    assert.equal(firstReadCalls, 0)
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(firstReadCalls, 0)
    releaseFirstFlush(true)
    submitted = await Promise.race([
      Promise.all([submittedPromise, captureCompletion]).then(([payload]) => payload),
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
  const captureMetrics = firstDispose.metrics()
  assert.equal(captureMetrics.capture_turns_seen, 1)
  assert.equal(captureMetrics.capture_turns_eligible, 1)
  assert.equal(captureMetrics.capture_events_committed, 1)

  const replayAgent = { session, model: firstAgent.model }
  const replayCalls = []
  let resolveRetried
  const retriedPromise = new Promise((resolve) => { resolveRetried = resolve })
  let retryCount = 0
  const replayContext = makeContext(() => {
    throw new Error('an accepted receipt must not re-extract')
  }, {
    agents: { get() { return undefined }, list() { return [replayAgent] } },
  })
  const replayDispose = apply(replayContext.ctx, config, async (_mode, payload, options) => {
    replayCalls.push({ payload, options })
    if (options.action === 'status') {
      return { status: retryCount ? 'COMMITTED' : 'ACCEPTED' }
    }
    if (options.action === 'retry') {
      retryCount += 1
      resolveRetried(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call during receipt recovery')
  })
  const replayCompletion = replayContext.handlers.get('session/event')(session, {
    type: 'turn/end',
    data: { turn: 1, reason: { kind: 'completed' } },
  })
  let recoveryTimer
  try {
    const replay = await Promise.race([
      Promise.all([replayCompletion, retriedPromise]).then(([, payload]) => payload),
      new Promise((_, reject) => { recoveryTimer = setTimeout(() => reject(new Error('recovery timed out')), 3000) }),
    ])
    assert.deepEqual(replay, { event_id: submitted.event_id })
    assert.ok(replayCalls.some((call) => call.options.action === 'status'))
    assert.equal(replayCalls.filter((call) => call.options.action === 'retry').length, 1)
  } finally {
    clearTimeout(recoveryTimer)
    replayDispose()
  }
})

test('fork recovery captures only child-owned turns', async () => {
  const parentEvents = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Parent fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'Parent ack.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  const childEvents = [
    { type: 'turn/start', seq: 5, data: { turn: 2 } },
    { type: 'user/message', seq: 6, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Child fact.' }],
    } },
    { type: 'assistant/message', seq: 7, data: {
      turn: 2,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'Child ack.' }],
      },
    } },
    { type: 'turn/end', seq: 8, data: { turn: 2, reason: { kind: 'completed' } } },
  ]
  const session = { id: 'fork-session', inheritedEventCount: 4 }
  const snapshot = { events: [...parentEvents, ...childEvents] }
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const handlers = new Map()
  let cleanup
  let forkRequest
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: {
      async *stream(request) {
        forkRequest = request
        yield {
          type: 'text-delta',
          text: JSON.stringify({
            memories: [{
              text: 'Child fact.',
              category: ['project'],
              importance: 0.8,
              replacement_intent: false,
            }],
            replacement_context: '',
          }),
        }
        yield { type: 'finish', reason: { kind: 'stop' } }
      },
    },
    sessions: { flush: async () => true },
    sessionQuery: { readSession: async () => snapshot },
    agents: { get() { return agent }, list() { return [agent] } },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const submitted = []
  let resolveSubmitted
  const submittedPromise = new Promise((resolve) => { resolveSubmitted = resolve })
  const dispose = apply(ctx, config, async (_mode, payload, options) => {
    if (options.action === 'status') return { status: 'NOT_FOUND' }
    if (options.action === 'submit') {
      submitted.push(payload)
      resolveSubmitted()
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  let timer
  try {
    await Promise.race([
      submittedPromise,
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('fork recovery timed out')), 3000) }),
    ])
    assert.equal(submitted.length, 1)
    assert.equal(submitted[0].event_id, compileTurn(childEvents, 'fork-session', 2).event_id)
    assert.equal(submitted[0].candidates[0].text, 'Child fact.')
    assert.match(forkRequest.messages[0].content[0].text, /Child fact/u)
    assert.match(forkRequest.messages[0].content[0].text, /Child ack/u)
    assert.doesNotMatch(forkRequest.messages[0].content[0].text, /Parent fact|Parent ack/u)
  } finally {
    clearTimeout(timer)
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

for (const takeoverTurn of [1, 2]) {
test(`agent takeover on turn ${takeoverTurn} recovers the executing capture once`, { timeout: 5000 }, async () => {
  const session = { id: 'dispose-drain-session' }
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember the disposal fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'Acknowledged.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  if (takeoverTurn === 2) {
    events.push(...structuredClone(events).map((event) => ({
      ...event,
      seq: event.seq + 4,
      data: { ...event.data, ...(Number.isInteger(event.data.turn) ? { turn: 2 } : {}) },
    })))
  }
  let extractionStarted
  const extractionGate = new Promise((resolve) => { extractionStarted = resolve })
  let releaseExtraction
  const finishExtraction = new Promise((resolve) => { releaseExtraction = resolve })
  const handlers = new Map()
  let cleanup
  let releaseStatus
  const statusGate = new Promise((resolve) => { releaseStatus = resolve })
  const submitted = []
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: {
      async *stream() {
        extractionStarted()
        await finishExtraction
        yield { type: 'text-delta', text: JSON.stringify({
          memories: [{
            text: 'Disposal fact.',
            category: ['project'],
            importance: 0.8,
            replacement_intent: false,
          }],
          replacement_context: '',
        }) }
        yield { type: 'finish', reason: { kind: 'stop' } }
      },
    },
    sessions: { flush: async () => true },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (_mode, payload, options) => {
    if (options.action === 'status') return statusGate
    if (options.action === 'submit') {
      submitted.push(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  try {
    handlers.get('agent/created')({ agent })
    const drain = handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    await new Promise((resolve) => setImmediate(resolve))
    handlers.get('agent/disposed')({ agent })
    const replacement = {
      session,
      model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
    }
    handlers.get('agent/created')({ agent: replacement })
    const replacementDrain = handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: takeoverTurn, reason: { kind: 'completed' } },
    })
    releaseStatus({ status: 'NOT_FOUND' })
    await extractionGate
    const repeatedRecovery = handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: takeoverTurn, reason: { kind: 'completed' } },
    })
    releaseExtraction()
    await Promise.all([drain, replacementDrain, repeatedRecovery])
    assert.equal(submitted.length, takeoverTurn)
    assert.equal(new Set(submitted.map((payload) => payload.event_id)).size, takeoverTurn)
    assert.ok(submitted.some((payload) => payload.event_id === compileTurn(events, session.id, 1).event_id))
    assert.equal(submitted[0].kind, 'turn_completed')
    assert.equal(dispose.metrics().capture_events_committed, takeoverTurn)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})
}

test('retained Owner receipts do not trigger re-extraction', async () => {
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember the retained fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'Acknowledged.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  for (const status of ['FAILED', 'PENDING', 'QUARANTINED']) {
    const handlers = new Map()
    let cleanup
    let extractionCalls = 0
    const session = { id: `retained-${status.toLowerCase()}` }
    const ctx = {
      on(event, handler) {
        handlers.set(event, handler)
        return () => handlers.delete(event)
      },
      effect(register) { cleanup = register() },
      logger: { warn() {} },
      llm: {
        async *stream() {
          extractionCalls += 1
          yield { type: 'finish', reason: { kind: 'stop' } }
        },
      },
      sessions: { flush: async () => true },
      sessionQuery: { readSession: async () => ({ events }) },
      agents: { get() { return undefined }, list() { return [] } },
    }
    const agent = {
      session,
      model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
    }
    const config = {
      ...DEFAULT_CONFIG,
      auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
    }
    const dispose = apply(ctx, config, async (_mode, _payload, options) => {
      if (options.action === 'status') return { status }
      throw new Error('retained receipts must not be submitted')
    })
    try {
      handlers.get('agent/created')({ agent })
      await handlers.get('session/event')(session, {
        type: 'turn/end',
        data: { turn: 1, reason: { kind: 'completed' } },
      })
      assert.equal(extractionCalls, 0, status)
      assert.equal(dispose.metrics().capture_failed, 1, status)
    } finally {
      dispose()
    }
    assert.equal(typeof cleanup, 'function', status)
    assert.equal(handlers.size, 0, status)
  }
})

test('an accepted receipt that remains failed is counted without re-extraction', async () => {
  const session = { id: 'accepted-failed-session' }
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember the accepted fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'Acknowledged.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  const handlers = new Map()
  let cleanup
  let extractionCalls = 0
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: {
      async *stream() {
        extractionCalls += 1
        yield { type: 'finish', reason: { kind: 'stop' } }
      },
    },
    sessions: { flush: async () => true },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (_mode, _payload, options) => {
    if (options.action === 'status') return { status: 'ACCEPTED' }
    if (options.action === 'retry') return { status: 'FAILED' }
    throw new Error('an accepted receipt must not be re-extracted')
  })
  try {
    handlers.get('agent/created')({ agent })
    await handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    assert.equal(extractionCalls, 0)
    assert.equal(dispose.metrics().capture_failed, 1)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

test('a non-committed submit is counted as a failed capture', async () => {
  const session = { id: 'submit-failed-session' }
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember the submit fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'Acknowledged.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  const handlers = new Map()
  let cleanup
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: {
      async *stream() {
        yield { type: 'text-delta', text: JSON.stringify({
          memories: [{
            text: 'Submit fact.',
            category: ['project'],
            importance: 0.8,
            replacement_intent: false,
          }],
          replacement_context: '',
        }) }
        yield { type: 'finish', reason: { kind: 'stop' } }
      },
    },
    sessions: { flush: async () => true },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (_mode, _payload, options) => {
    if (options.action === 'status') return { status: 'NOT_FOUND' }
    if (options.action === 'submit') return { status: 'FAILED' }
    throw new Error('unexpected Runtime call')
  })
  try {
    handlers.get('agent/created')({ agent })
    await handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    assert.equal(dispose.metrics().capture_failed, 1)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

test('disposing an agent that was never registered is harmless', () => {
  const handlers = new Map()
  let cleanup
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const dispose = apply(ctx, DEFAULT_CONFIG, async () => {
    throw new Error('unexpected Runtime call')
  })
  try {
    handlers.get('agent/disposed')({ agent: { session: { id: 'unknown-session' } } })
    assert.equal(handlers.size, 4)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

test('stalled DSH extraction times out and releases the capture worker', async () => {
  const session = { id: 'capture-timeout-session' }
  const events = []
  const firstTurnEvents = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember the first durable fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'The first fact is useful.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  const secondTurnEvents = [
    { type: 'turn/start', seq: 5, data: { turn: 2 } },
    { type: 'user/message', seq: 6, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember the second durable fact.' }],
    } },
    { type: 'assistant/message', seq: 7, data: {
      turn: 2,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'The second fact is useful.' }],
      },
    } },
    { type: 'turn/end', seq: 8, data: { turn: 2, reason: { kind: 'completed' } } },
  ]
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const handlers = new Map()
  const runtimeCalls = []
  const candidateOutput = JSON.stringify({ memories: [candidate], replacement_context: '' })
  let cleanup
  let extractionCalls = 0
  let timedOutSignal
  let resolveInitialRecoveryRead
  const initialRecoveryRead = new Promise((resolve) => { resolveInitialRecoveryRead = resolve })
  let sessionReads = 0
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    agents: { get() { return undefined }, list() { return [] } },
    llm: {
      stream(request) {
        extractionCalls += 1
        if (extractionCalls === 1) {
          timedOutSignal = request.signal
          return (async function* () { await new Promise(() => {}) })()
        }
        return (async function* () {
          yield { type: 'text-delta', text: candidateOutput }
          yield { type: 'finish', reason: { kind: 'stop' } }
        })()
      },
    },
    sessions: { async flush() { return true } },
    sessionQuery: {
      async readSession() {
        sessionReads += 1
        if (sessionReads === 1) resolveInitialRecoveryRead()
        return { events: [...events] }
      },
    },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true, timeout_ms: 1000 },
  }
  const dispose = apply(ctx, config, async (mode, payload, options) => {
    runtimeCalls.push({ mode, payload, options })
    return options.action === 'status' ? { status: 'NOT_FOUND' } : { status: 'COMMITTED' }
  })
  const waitFor = async (promise) => {
    let timer
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('capture worker did not settle')), 3000) }),
      ])
    } finally {
      clearTimeout(timer)
    }
  }
  try {
    handlers.get('agent/created')({ agent })
    await waitFor(initialRecoveryRead)
    events.push(...firstTurnEvents)
    await waitFor(handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    }))
    assert.equal(timedOutSignal.aborted, true)
    assert.equal(runtimeCalls.filter((call) => call.options.action === 'submit').length, 0)

    events.push(...secondTurnEvents)
    await waitFor(handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 2, reason: { kind: 'completed' } },
    }))
    assert.equal(extractionCalls, 2)
    assert.equal(runtimeCalls.filter((call) => call.options.action === 'submit').length, 1)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
})

test('disposing an agent cancels delayed recovery before it can enqueue Owner work', async () => {
  const events = [
    { type: 'turn/start', seq: 1, data: { turn: 1 } },
    { type: 'user/message', seq: 2, data: {
      source: { kind: 'user' },
      content: [{ type: 'text', text: 'Remember this durable fact.' }],
    } },
    { type: 'assistant/message', seq: 3, data: {
      turn: 1,
      message: {
        source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
        content: [{ type: 'text', text: 'I will remember it.' }],
      },
    } },
    { type: 'turn/end', seq: 4, data: { turn: 1, reason: { kind: 'completed' } } },
  ]
  const agent = {
    session: { id: 'disposed-recovery-session' },
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  let cleanup
  let readStarted
  const readStartedPromise = new Promise((resolve) => { readStarted = resolve })
  let releaseRead
  const readGate = new Promise((resolve) => { releaseRead = resolve })
  const handlers = new Map()
  const runtimeCalls = []
  let extractionCalls = 0
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    agents: { get() { return agent }, list() { return [agent] } },
    sessions: { async flush() { return true } },
    sessionQuery: {
      readSession() {
        readStarted()
        return readGate
      },
    },
    llm: {
      stream() {
        extractionCalls += 1
        throw new Error('disposed recovery must not start extraction')
      },
    },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (...args) => {
    runtimeCalls.push(args)
    return { status: 'NOT_FOUND' }
  })
  let timer
  try {
    await Promise.race([
      readStartedPromise,
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('recovery did not start')), 3000) }),
    ])
    handlers.get('agent/disposed')({ agent })
    releaseRead({ events })
    await new Promise((resolve) => setImmediate(resolve))
    handlers.get('session/event')(agent.session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    assert.equal(runtimeCalls.length, 0)
    assert.equal(extractionCalls, 0)
  } finally {
    clearTimeout(timer)
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
})

test('subagent sessions never recall or capture', async () => {
  const handlers = new Map()
  let cleanup
  const calls = []
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_recall: { ...DEFAULT_CONFIG.auto_recall, enabled: true },
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
    memory_injection: { ...DEFAULT_CONFIG.memory_injection, enabled: true },
  }
  const dispose = apply(ctx, config, async (mode, payload) => {
    calls.push({ mode, payload })
    return { memories: [] }
  })
  const subagent = {
    session: { id: 'subagent-session', header: { origin: 'subagent', delegationDepth: 1 } },
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const messages = [{
    role: 'user',
    source: { kind: 'user' },
    content: [{ type: 'text', text: 'Delegated child prompt.' }],
  }]
  const decision = { kind: 'enter', messages }
  try {
    handlers.get('agent/created')({ agent: subagent })
    const result = await handlers.get('agent/pre-step')(
      { agent: subagent, messages, turn: 1 },
      async () => decision,
    )
    assert.equal(result, decision)
    await handlers.get('session/event')(subagent.session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    assert.equal(calls.length, 0)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
})

test('subagent detection is independent for origin and delegation depth', async () => {
  const cases = [
    ['origin-only', { origin: 'subagent' }, true],
    ['depth-only', { delegationDepth: 1 }, true],
    ['parent', { delegationDepth: 0 }, false],
  ]
  for (const [label, header, blocked] of cases) {
    const handlers = new Map()
    let cleanup
    const calls = []
    const ctx = {
      on(event, handler) {
        handlers.set(event, handler)
        return () => handlers.delete(event)
      },
      effect(register) { cleanup = register() },
      logger: { warn() {} },
      agents: { get() { return undefined }, list() { return [] } },
    }
    const config = {
      ...DEFAULT_CONFIG,
      auto_recall: { ...DEFAULT_CONFIG.auto_recall, enabled: true },
      memory_injection: { ...DEFAULT_CONFIG.memory_injection, enabled: true },
    }
    const dispose = apply(ctx, config, async (mode, payload) => {
      calls.push({ mode, payload })
      return { memories: [{ id: 'm1', score: 0.9, text: 'A fact.' }] }
    })
    const agent = { session: { id: `case-${label}`, header } }
    const messages = [{
      role: 'user',
      source: { kind: 'user' },
      content: [{ type: 'text', text: `Query ${label}` }],
    }]
    const decision = { kind: 'enter', messages }
    try {
      handlers.get('agent/created')({ agent })
      const result = await handlers.get('agent/pre-step')(
        { agent, messages, turn: 1 },
        async () => decision,
      )
      if (blocked) {
        assert.equal(result, decision, label)
        assert.equal(calls.length, 0, label)
      } else {
        assert.equal(result.messages.length, 2, label)
        assert.equal(calls.length, 1, label)
      }
    } finally {
      dispose()
    }
    assert.equal(typeof cleanup, 'function', label)
    assert.equal(handlers.size, 0, label)
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
    llm: { stream() { throw new Error('must not call model when disabled') } },
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
  let runtimeCalls = 0
  const dispose = apply(ctx, config, async () => {
    runtimeCalls += 1
    throw new Error('synthetic outage')
  })
  handlers.get('agent/created')({ agent })
  const messages = [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'hello' }] }]
  try {
    const result = await handlers.get('agent/pre-step')({ agent, messages, turn: 1 }, async () => decision)
    assert.equal(result, decision)
    assert.equal(warningCount, 1)
    const retry = await handlers.get('agent/pre-step')({ agent, messages, turn: 1 }, async () => decision)
    assert.equal(retry, decision)
    assert.equal(runtimeCalls, 1)
  } finally {
    dispose()
  }
  assert.equal(typeof cleanup, 'function')
  assert.equal(handlers.size, 0)
  const metrics = dispose.metrics()
  assert.equal(metrics.recall_requests, 1)
  assert.equal(metrics.recall_failures, 1)
  assert.equal(metrics.recall_latency_ms_count, 1)
})

const turnEvents = (turn) => [
  { type: 'turn/start', seq: 4 * turn - 3, data: { turn } },
  { type: 'user/message', seq: 4 * turn - 2, data: {
    source: { kind: 'user' },
    content: [{ type: 'text', text: `Remember turn ${turn} fact.` }],
  } },
  { type: 'assistant/message', seq: 4 * turn - 1, data: {
    turn,
    message: {
      source: { kind: 'model', provider: 'provider-a', model: 'model-a' },
      content: [{ type: 'text', text: `Turn ${turn} acknowledged.` }],
    },
  } },
  { type: 'turn/end', seq: 4 * turn, data: { turn, reason: { kind: 'completed' } } },
]

const candidateStream = (text) => ({ async *stream() {
  yield { type: 'text-delta', text: JSON.stringify({
    memories: [{ text, category: ['project'], importance: 0.8, replacement_intent: false }],
    replacement_context: '',
  }) }
  yield { type: 'finish', reason: { kind: 'stop' } }
} })

test('the closing agent cannot reopen its own capture queue', async () => {
  const session = { id: 'self-reclaim-session' }
  const events = turnEvents(1)
  const handlers = new Map()
  let cleanup
  let releaseStatus
  const statusGate = new Promise((resolve) => { releaseStatus = resolve })
  const submitted = []
  const flushed = []
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: candidateStream('Remember turn 1 fact.'),
    sessions: { flush: async (queued) => { flushed.push(queued); return true } },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (_mode, payload, options) => {
    if (options.action === 'status') return statusGate
    if (options.action === 'submit') {
      submitted.push(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  try {
    handlers.get('agent/created')({ agent })
    const drain = handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    await new Promise((resolve) => setImmediate(resolve))
    handlers.get('agent/disposed')({ agent })
    const metricsAfterDispose = dispose.metrics()
    handlers.get('session/event')(session, {
      type: 'turn/end',
      data: { turn: 2, reason: { kind: 'completed' } },
    })
    assert.equal(dispose.metrics().capture_turns_seen, metricsAfterDispose.capture_turns_seen)
    releaseStatus({ status: 'NOT_FOUND' })
    await drain
    assert.equal(submitted.length, 1, 'only the pre-dispose turn submits once')
    assert.equal(dispose.metrics().capture_turns_seen, 1)
  } finally {
    dispose()
  }
  assert.equal(handlers.size, 0)
  assert.ok(flushed.every((queued) => queued === session))
})

test('a replacement agent flushes its own queued captures', async () => {
  const oldSession = { id: 'replacement-session' }
  const events = [...turnEvents(1), ...turnEvents(2)]
  const handlers = new Map()
  let cleanup
  let createdReplacement
  const replacementSeen = new Promise((resolve) => { createdReplacement = resolve })
  const replacementAgent = {
    get session() { createdReplacement(); return replacementAgent._session },
    set session(value) { replacementAgent._session = value },
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  let releaseStatus
  const statusGate = new Promise((resolve) => { releaseStatus = resolve })
  const submitted = []
  const flushed = []
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: candidateStream('Remember turn 1 fact.'),
    sessions: { flush: async (queued) => { flushed.push(queued); return true } },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session: oldSession,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (_mode, payload, options) => {
    if (options.action === 'status') return statusGate
    if (options.action === 'submit') {
      submitted.push(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  try {
    handlers.get('agent/created')({ agent })
    handlers.get('session/event')(oldSession, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    await new Promise((resolve) => setImmediate(resolve))
    handlers.get('agent/disposed')({ agent })
    const newSession = { id: 'replacement-session' }
    replacementAgent.session = newSession
    handlers.get('agent/created')({ agent: replacementAgent })
    await replacementSeen
    const replacementDrain = handlers.get('session/event')(newSession, {
      type: 'turn/end',
      data: { turn: 2, reason: { kind: 'completed' } },
    })
    releaseStatus({ status: 'NOT_FOUND' })
    await replacementDrain
    assert.equal(submitted.length, 2, 'the replacement agent finishes its own queued turn and takes over the pending one')
    // The executing capture that already started keeps the old session, while
    // every queued capture after the takeover flushes through the replacement
    // session identity.
    assert.ok(flushed.some((queued) => queued === newSession), 'the replacement identity is in use')
    assert.ok(flushed.at(-1) === newSession, 'the last queued capture flushes through the replacement session identity')
    assert.ok(dispose.metrics().capture_events_committed >= 2)
  } finally {
    dispose()
  }
  assert.equal(handlers.size, 0)
})

test('the capture boundary wait times out instead of blocking turns', { timeout: 6000 }, async () => {
  const handlers = new Map()
  let cleanup
  let warnings = []
  const never = new Promise(() => {})
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn(message) { warnings.push(String(message)) } },
    llm: { async *stream() { throw new Error('capture must stay disabled while the boundary stalls') } },
    sessions: { flush() { return never } },
    sessionQuery: { readSession() { return never } },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session: { id: 'stalled-boundary-session' },
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true, timeout_ms: 1000 },
  }
  const decision = { kind: 'enter', messages: [] }
  const dispose = apply(ctx, config, async () => { throw new Error('the Owner must never be called') })
  try {
    const started = Date.now()
    await handlers.get('agent/created')({ agent })
    await handlers.get('agent/pre-step')(
      { agent, messages: [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'hello' }] }], turn: 1 },
      async () => decision,
    )
    const elapsed = Date.now() - started
    // The active timeout_ms is 1000 ms; a wait that never unblocks would
    // exceed any bounded run.
    assert.ok(elapsed < 3000, `the decision must not hang behind the boundary wait (${elapsed} ms)`)
    assert.ok(warnings.some((message) => message.includes('capture boundary is unavailable')), warnings)
    // The watermark replacement keeps later turns unblocked too.
    const followUp = await handlers.get('agent/pre-step')(
      { agent, messages: [], turn: 2 },
      async () => decision,
    )
    assert.equal(followUp, decision)
  } finally {
    dispose()
  }
})

test('capture boundary initialization retries a missing durability handler', { timeout: 8000 }, async () => {
  const handlers = new Map()
  let cleanup
  let flushCalls = 0
  let durable = false
  setTimeout(() => { durable = true }, 700)
  const submitted = []
  const receipts = new Set()
  const events = turnEvents(1)
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: candidateStream('Remember turn 1 fact.'),
    sessions: { flush: async () => { flushCalls += 1; return durable } },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session: { id: 'late-durability-session' },
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true, timeout_ms: 5000 },
  }
  const dispose = apply(ctx, config, async (_mode, payload, options) => {
    if (options.action === 'status') {
      // The Owner keeps every submitted receipt idempotent, so the recovery
      // pass after the live capture sees the durable outcome.
      return { status: receipts.has(payload.event_id) ? 'COMMITTED' : 'NOT_FOUND' }
    }
    if (options.action === 'submit') {
      receipts.add(payload.event_id)
      submitted.push(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  try {
    await handlers.get('agent/created')({ agent })
    assert.ok(flushCalls > 1, `boundary initialization retried the handler (calls: ${flushCalls})`)
    handlers.get('session/event')(agent.session, {
      type: 'turn/end',
      data: { turn: 1, reason: { kind: 'completed' } },
    })
    await new Promise((resolve) => setTimeout(resolve, 300))
    assert.equal(submitted.length, 1, 'the live agent captures once durability appears, keeping its activation marker')
  } finally {
    dispose()
  }
  assert.equal(handlers.size, 0)
})

test('recovery replays only turns above the durable progress marker', async () => {
  const session = { id: 'progress-session' }
  const events = [
    ...turnEvents(1),
    {
      type: 'plugin:qdrant-memory/recovery-progress',
      seq: 5, ignorable: true, data: { session_id: 'progress-session', after_turn: 1 },
    },
    ...turnEvents(2),
  ]
  const handlers = new Map()
  let cleanup
  const statusCalls = []
  const submitted = []
  const ctx = {
    on(event, handler) {
      handlers.set(event, handler)
      return () => handlers.delete(event)
    },
    effect(register) { cleanup = register() },
    logger: { warn() {} },
    llm: candidateStream('Remember turn 1 fact.'),
    sessions: { flush: async () => true },
    sessionQuery: { readSession: async () => ({ events }) },
    agents: { get() { return undefined }, list() { return [] } },
  }
  const agent = {
    session,
    model: { current: () => ({ provider: 'provider-a', model: 'model-a' }) },
  }
  const config = {
    ...DEFAULT_CONFIG,
    auto_capture: { ...DEFAULT_CONFIG.auto_capture, enabled: true },
  }
  const dispose = apply(ctx, config, async (_mode, payload, options) => {
    if (options.action === 'status') {
      statusCalls.push(options)
      return { status: 'NOT_FOUND' }
    }
    if (options.action === 'submit') {
      submitted.push(payload)
      return { status: 'COMMITTED' }
    }
    throw new Error('unexpected Runtime call')
  })
  try {
    handlers.get('agent/created')({ agent })
    await new Promise((resolve) => setTimeout(resolve, 500))
    assert.equal(statusCalls.length, 1, 'turn 1 below the marker is never status-polled again')
    assert.equal(submitted.length, 1)
    assert.equal(submitted[0].event_id, compileTurn(events, session.id, 2).event_id)
  } finally {
    dispose()
  }
  assert.equal(handlers.size, 0)
  assert.ok(dispose.metrics().capture_recovery_count >= 1)
})
