// The bundled host module must bind one storage route per profile:
// legacy MCP through the published launcher, or one explicit Owner mode.
// Mirror the pack staging (#qdrant-native) from the native package and run
// the real plugin selection through a recording Host context.

import assert from 'node:assert/strict'
import { copyFile, mkdir, rm } from 'node:fs/promises'
import { isAbsolute } from 'node:path'
import test, { after, before } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

const bundleDir = fileURLToPath(new URL('../integrations/dsh/bundle/', import.meta.url))
const nativeSource = fileURLToPath(new URL('../integrations/dsh/native/index.js', import.meta.url))
const stagedNative = `${bundleDir}native/index.js`

// The pack step builds `#qdrant-native` from the native package source; this
// staged tree is generated for the suite and never committed.
let bundle

before(async () => {
  await mkdir(`${bundleDir}native`, { recursive: true })
  await copyFile(nativeSource, stagedNative)
  bundle = await import(pathToFileURL(`${bundleDir}index.js`).href)
})

after(async () => {
  await rm(`${bundleDir}native`, { recursive: true, force: true })
})

const recordingContext = () => {
  const plugins = []
  const listeners = new Set()
  const mcpRuntime = { fibers: [] }
  const register = (fiber) => {
    mcpRuntime.fibers.push(fiber)
    for (const listener of listeners) listener(fiber)
  }
  return {
    plugins,
    register,
    ctx: {
      tools: { definitions: () => [] },
      root: {
        on: (event, listener) => {
          assert.equal(event, 'internal/plugin')
          listeners.add(listener)
          return () => listeners.delete(listener)
        },
      },
      registry: { get: () => mcpRuntime },
      effect: (effect) => effect(),
      plugin: async (module, settings) => {
        if (settings?.serverName === 'qdrant-memory') register({ config: settings })
        plugins.push({ module, settings })
      },
    },
  }
}

/**
 * Owner activation resolves its endpoint through the runtime environment, so
 * the two Owner-mode tests run with a synthetic but strictly validated target.
 */
const withOwnerTargetEnv = (tests) => {
  const restored = { ...process.env }
  process.env.QDRANT_MEMORY_RUNTIME_PYTHON = process.execPath
  process.env.QDRANT_MEMORY_DSH_OWNER_URL = 'https://synthetic-owner.example/mcp'
  process.env.QDRANT_MEMORY_DSH_OWNER_TOKEN = 'synthetic-test-credential-'.repeat(3)
  after(() => {
    for (const key of ['QDRANT_MEMORY_RUNTIME_PYTHON', 'QDRANT_MEMORY_DSH_OWNER_URL', 'QDRANT_MEMORY_DSH_OWNER_TOKEN']) {
      delete process.env[key]
    }
    Object.assign(process.env, restored)
  })
  return tests()
}

withOwnerTargetEnv(() => {
  test('the bundle defaults to legacy mode with all three switches off', () => {
    assert.equal(bundle.Config({}).mode, 'legacy')
    const config = bundle.Config({})
    for (const key of ['auto_capture', 'auto_recall', 'memory_injection']) {
      assert.equal(config[key].enabled, false)
    }
  })

  test('legacy mode registers the published launcher through npx', async () => {
    const { ctx, plugins } = recordingContext()
    await bundle.apply(ctx, bundle.Config({}))
    assert.equal(plugins.length, 1)
    assert.equal(plugins[0].settings.transport, 'stdio')
    assert.equal(plugins[0].settings.serverName, 'qdrant-memory')
    assert.deepEqual(
      plugins[0].settings.args,
      ['-y', '@cnkang/qdrant-memory-launcher@0.1.0-rc.8', 'mcp', 'dsh'],
    )
  })

  test('legacy mode refuses automation before another transport starts', async () => {
    const config = bundle.Config({})
    await assert.rejects(
      bundle.apply(recordingContext().ctx, { ...config, auto_capture: { ...config.auto_capture, enabled: true } }),
      /Select native-owner or unified-owner/u,
    )
  })

  test('unknown storage modes stay rejected', async () => {
    await assert.rejects(
      bundle.apply(recordingContext().ctx, { ...bundle.Config({}), mode: 'unified' }),
      /Unknown Qdrant Memory storage mode/u,
    )
  })

  test('an existing qdrant-memory tool route blocks both Owner modes', async () => {
    const plugins = []
    const ctx = {
      tools: { definitions: () => [{ name: 'mcp__qdrant-memory__qdrant_memory_search' }] },
      plugin: async (module, settings) => { plugins.push({ module, settings }) },
    }
    for (const mode of ['native-owner', 'unified-owner']) {
      await assert.rejects(
        bundle.apply(ctx, { ...bundle.Config({}), mode }),
        /Remove the existing qdrant-memory MCP route/u,
      )
    }
    assert.equal(plugins.length, 0)
  })

  test('a reconnecting legacy route without current tools also blocks Owner activation', async () => {
    const reconnecting = { get: () => ({ fibers: [{ config: { serverName: 'qdrant-memory' } }] }) }
    await assert.rejects(
      bundle.apply(
        { tools: { definitions: () => [] }, registry: reconnecting },
        { ...bundle.Config({}), mode: 'native-owner' },
      ),
      /Remove the existing qdrant-memory MCP route/u,
    )
  })

  test('native-owner activates the native plugin alone', async () => {
    assert.ok(isAbsolute(process.env.QDRANT_MEMORY_RUNTIME_PYTHON))
    const { ctx, plugins, register } = recordingContext()
    await bundle.apply(ctx, { ...bundle.Config({}), mode: 'native-owner' })
    assert.equal(plugins.length, 1)
    assert.equal(plugins[0].module.name, 'qdrant-memory-dsh-native')
    assert.throws(
      () => register({ config: { serverName: 'qdrant-memory', transport: 'stdio' } }),
      /only one qdrant-memory MCP route/u,
    )
  })

  test('unified-owner binds the streamable HTTP Owner and the native plugin', async () => {
    const { ctx, plugins, register } = recordingContext()
    await bundle.apply(ctx, { ...bundle.Config({}), mode: 'unified-owner' })
    assert.equal(plugins.length, 2)
    assert.equal(plugins[0].settings.transport, 'streamable-http')
    assert.equal(plugins[0].settings.url, process.env.QDRANT_MEMORY_DSH_OWNER_URL)
    assert.equal(plugins[0].settings.failOnStartupError, true)
    assert.equal(plugins[0].settings.headers.Authorization, `Bearer ${process.env.QDRANT_MEMORY_DSH_OWNER_TOKEN}`)
    assert.equal(plugins[1].module.name, 'qdrant-memory-dsh-native')
    assert.throws(
      () => register({ config: { serverName: 'qdrant-memory', transport: 'stdio' } }),
      /only one qdrant-memory MCP route/u,
    )
  })
})
