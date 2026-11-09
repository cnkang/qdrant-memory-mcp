import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { killProcessTree } from './kill-process-tree.mjs'

const windows = process.platform === 'win32'
const dsh = windows ? (process.env.ComSpec || 'cmd.exe') : 'dsh'
const shellArgs = (args) => (windows ? ['/d', '/s', '/c', `dsh ${args.join(' ')}`] : args)
const home = mkdtempSync(join(tmpdir(), 'dsh-native-ci-'))
const env = { ...process.env, DSH_HOME: home }

/** Run DSH in the isolated test home and return a failure status on timeout. */
const runDsh = (args) => {
  const result = spawnSync(dsh, shellArgs(args), {
    cwd: process.cwd(),
    env,
    encoding: 'utf8',
    shell: false,
    detached: !windows,
    timeout: 120000,
  })
  if (result.error) {
    killProcessTree(result.pid)
    console.error(`DSH command could not start: ${result.error.code || 'unknown'}`)
    return 1
  }
  if (result.stdout) process.stdout.write(result.stdout)
  if (result.stderr) process.stderr.write(result.stderr)
  return result.status ?? 1
}

let status
try {
  status = runDsh(['plugin', '--profile', 'qdrant-native-ci', 'add', '.'])
  if (status === 0) {
    const validation = spawnSync(process.execPath, ['./scripts/validate-host-config.mjs'], {
      cwd: process.cwd(),
      env,
      encoding: 'utf8',
      shell: false,
      detached: !windows,
      timeout: 60000,
    })
    if (validation.error) killProcessTree(validation.pid)
    if (validation.stdout) process.stdout.write(validation.stdout)
    if (validation.stderr) process.stderr.write(validation.stderr)
    status = validation.error ? 1 : (validation.status ?? 1)
  }
} finally {
  const removal = runDsh([
    'plugin',
    '--profile',
    'qdrant-native-ci',
    'remove',
    '@cnkang/qdrant-memory-dsh-native',
  ])
  if (status === 0) status = removal
  let cleanupError
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      rmSync(home, { recursive: true, force: true })
      cleanupError = undefined
      break
    } catch (error) {
      cleanupError = error
      if (attempt < 2) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100)
    }
  }
  if (cleanupError) {
    console.error(`DSH temporary home cleanup failed: ${cleanupError.code || 'unknown'}`)
    if (status === 0) status = 1
  }
}
process.exit(status)
