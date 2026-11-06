import assert from 'node:assert/strict'

const [major, minor] = process.versions.node.split('.').map(Number)

assert.ok(
  major === 24 && minor >= 9,
  `the native DSH validation lane requires Node.js 24.9.0 or newer within Node.js 24; received ${process.version}`,
)
