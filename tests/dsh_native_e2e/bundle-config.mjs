import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'
import { join } from 'node:path'

// Invoked against the module installed by the official Plugin Manager from tgz.
const installAnchor = join(process.env.DSH_TEST_MODULES, '@deepseek-ai/dsh/package.json')
const require = createRequire(installAnchor)
const Boot = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')))
const { Context } = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis')))
const root = new Context()
await root.plugin(Boot.PluginPackages, { resolution: await Boot.createRuntimeResolution({
  installAnchor, home: process.env.DSH_HOME,
  profile: Boot.loadProfileDirectory('dsh', process.argv[3], installAnchor),
}) })
const Bundle = await import(pathToFileURL(process.argv[2]))
const config = Bundle.Config({})
assert.equal(config.mode, 'legacy')
for (const key of ['auto_capture', 'auto_recall', 'memory_injection']) assert.equal(config[key].enabled, false)
const calls = []
const ctx = {
  root,
  effect: root.effect.bind(root),
  tools: { definitions: () => [] },
  plugin: async (module, settings) => { calls.push({ module, settings }) },
}
await Bundle.apply(ctx, config)
assert.equal(calls.length, 1)
assert.equal(calls[0].settings.transport, 'stdio')
assert.equal(calls[0].settings.serverName, 'qdrant-memory')
assert.deepEqual(calls[0].settings.args, ['-y', '@cnkang/qdrant-memory-launcher@0.1.0-rc.9', 'mcp', 'dsh'])
await assert.rejects(Bundle.apply(ctx, { ...config, auto_capture: { ...config.auto_capture, enabled: true } }))
assert.equal(calls.length, 1, 'legacy mode must reject automation before another transport starts')
process.env.QDRANT_MEMORY_RUNTIME_PYTHON = process.execPath
process.env.QDRANT_MEMORY_DSH_OWNER_URL = 'https://synthetic-owner.example/mcp'
process.env.QDRANT_MEMORY_DSH_OWNER_TOKEN = 'synthetic-test-credential-'.repeat(3)
await Bundle.apply(ctx, { ...config, mode: 'unified-owner' })
assert.equal(calls.length, 3)
assert.equal(calls[1].settings.transport, 'streamable-http')
assert.equal(calls[1].settings.url, process.env.QDRANT_MEMORY_DSH_OWNER_URL)
assert.equal(calls[1].settings.headers.Authorization, `Bearer ${process.env.QDRANT_MEMORY_DSH_OWNER_TOKEN}`)
assert.equal(calls[2].module.name, 'qdrant-memory-dsh-native')
await Bundle.apply(ctx, { ...config, mode: 'native-owner' })
assert.equal(calls.length, 4)
assert.equal(calls[3].module.name, 'qdrant-memory-dsh-native')
ctx.tools.definitions = () => [{ name: 'mcp__qdrant-memory__qdrant_memory_search' }]
for (const mode of ['native-owner', 'unified-owner']) {
  await assert.rejects(Bundle.apply(ctx, { ...config, mode }), /Remove the existing/u)
}
assert.equal(calls.length, 4, 'an existing Legacy route must block Owner activation before another connection starts')
console.log('Installed bundle: legacy defaults, mode refusal and one unified Owner target verified')
await root.fiber.dispose()
