import { spawnSync } from 'node:child_process'

/**
 * Terminate one timed-out process tree and briefly await its exit.
 *
 * Windows kills only the direct child, so a command wrapper such as cmd.exe
 * would otherwise leave the DSH CLI running while the validator tears down
 * the profile it is still writing. POSIX uses its detached process group.
 */
export function killProcessTree(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { shell: false })
  } else {
    try {
      process.kill(-pid, 'SIGKILL')
    } catch {
      try { process.kill(pid, 'SIGKILL') } catch { /* Already exited. */ }
    }
  }
  const deadline = Date.now() + 2000
  while (Date.now() < deadline) {
    try {
      process.kill(pid, 0)
    } catch (error) {
      if (error.code === 'ESRCH') return
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100)
  }
}
