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

/**
 * Whether the legacy qdrant-memory route is still active in this profile.
 * Tool definitions alone cannot rule out a live route: a reconnecting
 * McpClient keeps its registered fibers while its tools are absent between
 * connection attempts, so plugin registration is the durable lifecycle.
 */
function legacyRouteRegistered(ctx) {
  if (ctx.tools.definitions().some((tool) => tool.name.startsWith('mcp__qdrant-memory__'))) return true
  const runtime = ctx.registry?.get?.(McpClient)
  for (const fiber of runtime?.fibers ?? []) {
    if (fiber?.config?.serverName === 'qdrant-memory') return true
  }
  return false
}

/** Keep late MCP registrations from creating a second storage route. */
function guardLateLegacyRoute(ctx, target) {
  let ownerRegistrationOpen = false
  let ownerRouteRegistered = false
  const allowedOwnerFibers = new WeakSet()
  const rejected = new WeakSet()
  const dispose = ctx.root.on('internal/plugin', (fiber) => {
    const runtime = ctx.registry?.get?.(McpClient)
    let isMcpFiber = false
    for (const candidate of runtime?.fibers ?? []) {
      if (candidate === fiber) {
        isMcpFiber = true
        break
      }
    }
    if (!isMcpFiber || fiber?.config?.serverName !== 'qdrant-memory') return
    if (allowedOwnerFibers.has(fiber)) return
    const route = fiber.config
    if (ownerRegistrationOpen && !ownerRouteRegistered
      && route.transport === 'streamable-http'
      && route.url === target.endpoint
      && route.headers?.Authorization === `Bearer ${target.token}`) {
      ownerRouteRegistered = true
      allowedOwnerFibers.add(fiber)
      return
    }
    if (rejected.has(fiber)) return
    rejected.add(fiber)
    throw new Error('An Owner mode profile can have only one qdrant-memory MCP route')
  })
  ctx.effect(() => dispose)
  return {
    beginOwnerRegistration() { ownerRegistrationOpen = true },
    endOwnerRegistration() { ownerRegistrationOpen = false },
  }
}

/** Select one storage target for the entire profile; never open a second writer. */
export async function apply(ctx, config) {
  const enabled = config.auto_capture.enabled || config.auto_recall.enabled || config.memory_injection.enabled
  if (config.mode === 'legacy') {
    if (enabled) throw new Error('Select native-owner or unified-owner explicitly before enabling automatic memory')
    await ctx.plugin(McpClient, {
      serverName: 'qdrant-memory', transport: 'stdio', command: 'npx',
      args: ['-y', '@cnkang/qdrant-memory-launcher@0.1.0-rc.9', 'mcp', 'dsh'],
    })
    return
  }
  if (!['native-owner', 'unified-owner'].includes(config.mode)) throw new Error('Unknown Qdrant Memory storage mode')
  if (legacyRouteRegistered(ctx)) {
    throw new Error('Remove the existing qdrant-memory MCP route before selecting an Owner mode')
  }
  const target = Native.runtimeTarget(process.env)
  const routeGuard = guardLateLegacyRoute(ctx, target)
  if (config.mode === 'unified-owner') {
    routeGuard.beginOwnerRegistration()
    try {
      await ctx.plugin(McpClient, {
        serverName: 'qdrant-memory', transport: 'streamable-http', url: target.endpoint,
        headers: { Authorization: `Bearer ${target.token}` }, failOnStartupError: true,
      })
    } finally {
      routeGuard.endOwnerRegistration()
    }
  }
  await ctx.plugin(Native, config)
}
