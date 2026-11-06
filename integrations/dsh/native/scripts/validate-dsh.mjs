import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const packageJson = JSON.parse(readFileSync(
  new URL('../node_modules/@deepseek-ai/dsh/package.json', import.meta.url),
  'utf8',
))
const version = packageJson.version
assert.equal(version, '0.2.2-rc.1', 'the native validation lane must use DSH 0.2.2-rc.1')
