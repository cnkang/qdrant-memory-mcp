import assert from 'node:assert/strict'
import { execSync } from 'node:child_process'

const version = execSync('dsh --version', { encoding: 'utf8' }).trim()
assert.equal(version, '0.2.2-rc.1', 'the native validation lane must use DSH 0.2.2-rc.1')
