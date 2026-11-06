import assert from 'node:assert/strict'
import { execSync } from 'node:child_process'

const version = execSync('pnpm --version', { encoding: 'utf8' }).trim()
assert.equal(version, '11.28.5', 'the DSH Plugin Manager validation lane must use pnpm 11.28.5')
