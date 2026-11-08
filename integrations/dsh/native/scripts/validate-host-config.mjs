import { spawnSync } from 'node:child_process'

const result = spawnSync('dsh', ['--profile', 'qdrant-native-ci', '--dump-config'], {
  encoding: 'utf8',
  shell: false,
})

if (result.status !== 0) {
  console.error('DSH profile config dump failed')
  console.error((result.stderr || '').slice(0, 2000))
  process.exit(1)
}

const text = `${result.stdout || ''}\n${result.stderr || ''}`
const pluginAt = text.indexOf('id: qdrant-memory-native')
if (pluginAt < 0) {
  console.error('DSH profile config does not contain qdrant-memory-native')
  process.exit(1)
}

const body = text.slice(pluginAt)
for (const key of ['auto_recall', 'auto_capture', 'memory_injection']) {
  const pattern = new RegExp(`${key}:[\\s\\S]{0,200}?enabled:\\s*false`, 'u')
  if (!pattern.test(body)) {
    console.error(`DSH profile config does not keep ${key}.enabled=false`)
    process.exit(1)
  }
}

console.log('DSH native profile config contains the plugin and all three default-off switches')
