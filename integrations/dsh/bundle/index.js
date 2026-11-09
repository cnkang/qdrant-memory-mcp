import Schema from '@deepseek-ai/schemastery'
import * as McpClient from '@deepseek-ai/dsh-mcp-client'
import * as Native from '#qdrant-native'

const [major, minor] = process.versions.node.split('.').map(Number)
if (major < 24 || (major === 24 && minor < 9)) {
  throw new Error('Qdrant Memory Bundle 0.2 requires Node.js >=24.9.0; use Bundle 0.1.6 on older Hosts')
}

export const name = 'qdrant-memory-dsh-bundle'
export const inject = ['tools']
export const Config = Schema.intersect([
  Native.Config,
  Schema.object({
    mode: Schema.union(['legacy', 'native-owner', 'unified-owner']).default('legacy'),
  }),
])

/** Select one storage target for the entire profile; never open a second writer. */
export async function apply(ctx, config) {
  const enabled = config.auto_capture.enabled || config.auto_recall.enabled || config.memory_injection.enabled
  if (config.mode === 'legacy') {
    if (enabled) throw new Error('Select native-owner or unified-owner explicitly before enabling automatic memory')
    await ctx.plugin(McpClient, {
      serverName: 'qdrant-memory', transport: 'stdio', command: 'npx',
      args: ['-y', '@cnkang/qdrant-memory-launcher@0.1.0-rc.8', 'mcp', 'dsh'],
    })
    return
  }
  if (!['native-owner', 'unified-owner'].includes(config.mode)) throw new Error('Unknown Qdrant Memory storage mode')
  if (ctx.tools.definitions().some((tool) => tool.name.startsWith('mcp__qdrant-memory__'))) {
    throw new Error('Remove the existing qdrant-memory MCP route before selecting an Owner mode')
  }
  const target = Native.runtimeTarget(process.env)
  if (config.mode === 'unified-owner') {
    await ctx.plugin(McpClient, {
      serverName: 'qdrant-memory', transport: 'streamable-http', url: target.endpoint,
      headers: { Authorization: `Bearer ${target.token}` }, failOnStartupError: true,
    })
  }
  await ctx.plugin(Native, config)
}
