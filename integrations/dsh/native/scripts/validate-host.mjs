import { spawn, spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { killProcessTree } from './kill-process-tree.mjs'

const windows = process.platform === 'win32'
const dsh = windows ? (process.env.ComSpec || 'cmd.exe') : 'dsh'
const shellArgs = (args) => (windows ? ['/d', '/s', '/c', `dsh ${args.join(' ')}`] : args)
const home = mkdtempSync(join(tmpdir(), 'dsh-native-ci-'))
const env = { ...process.env, DSH_HOME: home }

/** Run DSH and terminate its whole process tree before cleaning its test home. */
const runDsh = (args) => new Promise((resolve) => {
  const child = spawn(dsh, shellArgs(args), {
    cwd: process.cwd(),
    env,
    shell: false,
    detached: !windows,
    stdio: 'inherit',
    windowsHide: true,
  })
  let timedOut = false
  let spawnError
  let timer
  child.once('spawn', () => {
    timer = setTimeout(() => {
      timedOut = true
      try { killProcessTree(child.pid) } catch { /* Fall back to terminating the direct child. */ }
      if (child.exitCode === null && child.signalCode === null) {
        try { child.kill('SIGKILL') } catch { /* The process exited while termination was starting. */ }
      }
    }, 120000)
  })
  child.once('error', (error) => { spawnError = error })
  child.once('close', (code) => {
    clearTimeout(timer)
    if (timedOut) console.error('DSH command timed out')
    else if (spawnError) console.error(`DSH command could not start: ${spawnError.code || 'unknown'}`)
    resolve(timedOut || spawnError ? 1 : (code ?? 1))
  })
})

let status
try {
  status = await runDsh(['plugin', '--profile', 'qdrant-native-ci', 'add', '.'])
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
  const removal = await runDsh([
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
