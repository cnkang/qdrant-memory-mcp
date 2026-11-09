import { spawnSync } from 'node:child_process'

const windows = process.platform === 'win32'
const command = windows ? (process.env.ComSpec || 'cmd.exe') : 'dsh'
const args = windows
  ? ['/d', '/s', '/c', 'dsh --profile qdrant-native-ci --dump-config']
  : ['--profile', 'qdrant-native-ci', '--dump-config']
const result = spawnSync(command, args, {
  encoding: 'utf8',
  shell: false,
  timeout: 30000,
})

if (result.error) {
  console.error(`DSH profile config command could not start: ${result.error.code || 'unknown'}`)
  process.exit(1)
}
if (result.status !== 0) {
  console.error('DSH profile config dump failed')
  console.error((result.stderr || '').slice(0, 2000))
  process.exit(1)
}

const text = `${result.stdout || ''}\n${result.stderr || ''}`
const lines = text.split('\n')
const pluginAt = lines.findIndex((line) => /^\s*-\s*id:\s*qdrant-memory-native\s*$/u.test(line))
if (pluginAt < 0) {
  console.error('DSH profile config does not contain qdrant-memory-native')
  process.exit(1)
}

const indentOf = (line) => (line.match(/^\s*/u) || [''])[0].length
const pluginIndent = indentOf(lines[pluginAt])
let pluginEnd = lines.length
for (let cursor = pluginAt + 1; cursor < lines.length; cursor += 1) {
  const line = lines[cursor]
  if (!line.trim()) continue
  if (indentOf(line) <= pluginIndent
    && (/^\s*-\s*id:/u.test(line) || indentOf(line) < pluginIndent)) {
    pluginEnd = cursor
    break
  }
}
const bodyLines = lines.slice(pluginAt, pluginEnd)

/** Return whether the named section has a direct enabled=false setting. */
const sectionEnabled = (key) => {
  const heading = new RegExp(`^\\s*${key}:\\s*$`, 'u')
  const index = bodyLines.findIndex((line) => heading.test(line))
  if (index < 0) return null
  const indent = indentOf(bodyLines[index])
  let childIndent = null
  for (let cursor = index + 1; cursor < bodyLines.length; cursor += 1) {
    if (!bodyLines[cursor].trim()) continue
    if (indentOf(bodyLines[cursor]) <= indent) break
    childIndent = indentOf(bodyLines[cursor])
    break
  }
  if (childIndent === null) return null
  // Only the section's direct `enabled` key counts; a nested subsection may
  // have its own enabled flag and must not satisfy this check.
  for (let cursor = index + 1; cursor < bodyLines.length; cursor += 1) {
    const line = bodyLines[cursor]
    if (!line.trim()) continue
    const lineIndent = indentOf(line)
    if (lineIndent < childIndent) break
    if (lineIndent !== childIndent) continue
    const enabled = line.match(/^\s*enabled:\s*(true|false)\s*$/u)
    if (enabled) return enabled[1] === 'false'
  }
  return null
}

for (const key of ['auto_recall', 'auto_capture', 'memory_injection']) {
  if (sectionEnabled(key) !== true) {
    console.error(`DSH profile config does not keep ${key}.enabled=false`)
    process.exit(1)
  }
}

console.log('DSH native profile config contains the plugin and all three default-off switches')
