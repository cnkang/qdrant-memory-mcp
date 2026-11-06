import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const packageJsonPath = process.env.QDRANT_MEMORY_DSH_PACKAGE_JSON
  ?? new URL('../node_modules/@deepseek-ai/dsh/package.json', import.meta.url)
const packageJson = JSON.parse(readFileSync(
  packageJsonPath,
  'utf8',
))
const version = packageJson.version
assert.equal(version, '0.2.2-rc.1', 'the native validation lane must use DSH 0.2.2-rc.1')
