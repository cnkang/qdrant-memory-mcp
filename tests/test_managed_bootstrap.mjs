import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';

import { command, extractExecutable, verifyArtifact } from '../integrations/managed/bootstrap.mjs';

function wheel(name = 'uv-0.13.1.data/scripts/uv', type = 0o100755) {
  const data = Buffer.from('synthetic executable');
  const filename = Buffer.from(name);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt32LE(data.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(filename.length, 26);
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt32LE(data.length, 20);
  central.writeUInt32LE(data.length, 24);
  central.writeUInt16LE(filename.length, 28);
  central.writeUInt32LE((type * 65536) >>> 0, 38);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(1, 8);
  end.writeUInt16LE(1, 10);
  end.writeUInt32LE(central.length + filename.length, 12);
  end.writeUInt32LE(local.length + filename.length + data.length, 16);
  return Buffer.concat([local, filename, data, central, filename, end]);
}

test('verify the whole artifact before reading an executable', () => {
  const bytes = wheel();
  const spec = { size: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
  assert.equal(verifyArtifact(bytes, spec), bytes);
  assert.throws(() => verifyArtifact(Buffer.from('corrupt'), spec));
  assert.throws(() => verifyArtifact(bytes, { ...spec, sha256: '0'.repeat(64) }));
});

test('extract one exact regular file without following archive paths', () => {
  assert.equal(extractExecutable(wheel(), 'uv-0.13.1.data/scripts/uv').toString(), 'synthetic executable');
  assert.throws(() => extractExecutable(wheel('other'), 'uv-0.13.1.data/scripts/uv'));
  assert.throws(() => extractExecutable(wheel('other/uv'), 'uv-0.13.1.data/scripts/uv'));
  assert.throws(() => extractExecutable(wheel('other/uv'), 'uv'));
});

for (const [stderr, category] of [
  ['invalid peer certificate: UnknownIssuer', 'certificate'],
  ['Permission denied (os error 13)', 'permission'],
  ['No download found for request on unsupported platform', 'platform'],
  ['Failed to lookup address: DNS error', 'network'],
  ['connection timed out', 'timeout'],
  ['unexpected failure', 'subprocess'],
]) {
  test(`report safe ${category} command diagnostics`, () => {
    const secret = 'https://user:synthetic-password@example.invalid/?token=synthetic-token';
    assert.throws(() => command(process.execPath,
      ['-e', 'process.stderr.write(process.argv[1]); process.exit(1)', `${stderr} ${secret}`],
      process.env, 10000), error => {
      assert.equal(error.category, category);
      assert.equal(error.stage, 'python-execute');
      assert.equal(error.exitCode, 1);
      assert.doesNotMatch(JSON.stringify(error) + error.message, /synthetic-|example\.invalid/);
      return true;
    });
  });
}

test('classify a subprocess timeout without exposing the spawn error', () => {
  assert.throws(() => command(process.execPath, ['-e', 'setInterval(() => {}, 1000)'],
    process.env, 50), error => {
    assert.equal(error.category, 'timeout');
    assert.equal(error.exitCode, null);
    return true;
  });
});

for (const name of ['../uv', '/uv', 'C:\\uv', 'safe/../../uv']) {
  test(`reject unsafe archive path ${name}`, () => {
    assert.throws(() => extractExecutable(wheel(name), name));
  });
}

test('reject archive symlinks and corrupt local/central offsets', () => {
  assert.throws(() => extractExecutable(wheel('uv', 0o120777), 'uv'));
  const bytes = wheel();
  bytes.writeUInt32LE(0xffffffff, bytes.length - 6);
  assert.throws(() => extractExecutable(bytes, 'uv-0.13.1.data/scripts/uv'));
});

test('reject encrypted entries', () => {
  const bytes = wheel();
  const offset = bytes.readUInt32LE(bytes.length - 6);
  bytes.writeUInt16LE(1, offset + 8);
  assert.throws(() => extractExecutable(bytes, 'uv-0.13.1.data/scripts/uv'));
});

test('reject unsupported compression and oversized executable entries', () => {
  for (const [field, value] of [[10, 99], [24, 65 * 1024 * 1024]]) {
    const bytes = wheel();
    const offset = bytes.readUInt32LE(bytes.length - 6);
    if (field === 10) bytes.writeUInt16LE(value, offset + field);
    else bytes.writeUInt32LE(value, offset + field);
    assert.throws(() => extractExecutable(bytes, 'uv-0.13.1.data/scripts/uv'));
  }
});

test('reject mismatched local file names and truncated archives', () => {
  const bytes = wheel();
  bytes[30] = 'X'.charCodeAt(0);
  assert.throws(() => extractExecutable(bytes, 'uv-0.13.1.data/scripts/uv'));
  assert.throws(() => extractExecutable(bytes.subarray(0, 50), 'uv-0.13.1.data/scripts/uv'));
});
