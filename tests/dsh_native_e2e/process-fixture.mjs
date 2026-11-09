import assert from 'node:assert/strict'
import test from 'node:test'
import { harness, until } from './agent-loop.test.mjs'

test('persisted process fixture', { timeout: 10000 }, async (t) => {
  const h = await harness(t, {}, process.env.QM_DSH_PROCESS_ROOT)
  if (process.env.QM_DSH_PROCESS_PHASE === 'prepare') {
    h.ownerState.unavailable = true
    const agent = await h.create('iris-process-restart')
    for (let index = 0; index < 8; index++) await h.send(agent, 'Synthetic Project Iris uses SQLite WAL.')
    await h.ctx.sessions.flush(agent.session)
    await h.plugin.dispose()
    assert.equal(h.receipts.length, 0)
  } else {
    const resumed = await h.ctx.agents.resume({ resumeSessionId: 'iris-process-restart',
      agentOptions: { provider: 'acceptance', model: 'synthetic' },
    })
    await until(() => h.receipts.length === 8, 'receipt recovery after full process restart')
    assert.equal(new Set(h.receipts.map((r) => r.event_id)).size, 8)
    await resumed.dispose()
  }
})
