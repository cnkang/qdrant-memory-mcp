/** Prerequisite PoC: verified managed Python using only Node and OS facilities.
 * This is not the production WorkBuddy launcher and does not initialize memory.
 */
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, realpath, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative, isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import { inflateRawSync } from 'node:zlib';

const UV_VERSION = '0.13.1';
const PYTHON_VERSION = '3.11.15';
// Official PyPI uv wheels. The entire artifact is checked before ZIP parsing.
const BOOTSTRAPS = {
  'darwin-arm64': {
    url: 'https://files.pythonhosted.org/packages/3b/31/fad7fd2ac81954d02d33765bf8535eb320fcc2d71f2603a5c1ba0b13b8ef/uv-0.13.1-py3-none-macosx_11_0_arm64.whl',
    sha256: 'cfa719fbbd23f26713394dea2692b7f146aa1b5713ce5e776e878701214ea52c', size: 14391237,
  },
  'darwin-x64': {
    url: 'https://files.pythonhosted.org/packages/db/3d/6ac43d7a15be1d589aae1e15289507f5ccebeac14f28c37882058f2474a3/uv-0.13.1-py3-none-macosx_10_12_x86_64.whl',
    sha256: '7e60223e3e9636a3734d6c11b3552aeed987c40f1ca2497a546af58f2f883d56', size: 17663254,
  },
  'linux-x64': {
    url: 'https://files.pythonhosted.org/packages/14/0b/6602a613533602e7a083e908c4375f9b0e78a94ba2e21c29b21c41a0a611/uv-0.13.1-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl',
    sha256: '696dcf6d807d85da978f4db8472da81dccc1254b18b52cbd1367c4d923c421e0', size: 17279385,
  },
  'win32-x64': {
    url: 'https://files.pythonhosted.org/packages/2a/8e/d23278bb327d2a75dc1d033c81b7fe23bbb28e363e02e7f306abd047924a/uv-0.13.1-py3-none-win_amd64.whl',
    sha256: '4f693cd4feb52f08f30474c4612f24be2050472609be65b9960b635f286da284', size: 15404994,
  },
};

export function verifyArtifact(bytes, spec) {
  if (bytes.length !== spec.size || createHash('sha256').update(bytes).digest('hex') !== spec.sha256) {
    throw new Error('Bootstrap artifact integrity mismatch');
  }
  return bytes;
}

function bounds(bytes, offset, size) {
  if (!Number.isSafeInteger(offset) || offset < 0 || size < 0 || offset + size > bytes.length) {
    throw new Error('Invalid ZIP bounds');
  }
}

export function extractExecutable(bytes, expectedName) {
  // Read one regular file into memory. No archive paths are written to disk.
  let end = -1;
  for (let cursor = bytes.length - 22; cursor >= Math.max(0, bytes.length - 65557); cursor--) {
    if (bytes.readUInt32LE(cursor) === 0x06054b50) { end = cursor; break; }
  }
  if (end < 0) throw new Error('ZIP end record missing');
  const count = bytes.readUInt16LE(end + 10);
  const centralSize = bytes.readUInt32LE(end + 12);
  let cursor = bytes.readUInt32LE(end + 16);
  bounds(bytes, cursor, centralSize);
  if (!count || count > 1000 || bytes.readUInt16LE(end + 4) || bytes.readUInt16LE(end + 6)
      || bytes.readUInt16LE(end + 8) !== count || cursor + centralSize !== end) {
    throw new Error('Unsupported ZIP layout');
  }
  let executable;
  for (let index = 0; index < count; index++) {
    bounds(bytes, cursor, 46);
    if (bytes.readUInt32LE(cursor) !== 0x02014b50) throw new Error('Invalid ZIP directory');
    const flags = bytes.readUInt16LE(cursor + 8);
    const method = bytes.readUInt16LE(cursor + 10);
    const compressed = bytes.readUInt32LE(cursor + 20);
    const expanded = bytes.readUInt32LE(cursor + 24);
    const nameSize = bytes.readUInt16LE(cursor + 28);
    const extraSize = bytes.readUInt16LE(cursor + 30);
    const commentSize = bytes.readUInt16LE(cursor + 32);
    const mode = bytes.readUInt32LE(cursor + 38) >>> 16;
    const localOffset = bytes.readUInt32LE(cursor + 42);
    bounds(bytes, cursor + 46, nameSize + extraSize + commentSize);
    const name = bytes.subarray(cursor + 46, cursor + 46 + nameSize).toString('utf8');
    if (name.startsWith('/') || /^[A-Za-z]:/.test(name) || name.includes('\\') || name.includes('\0')
        || name.split('/').includes('..') || (mode & 0xf000) === 0xa000 || flags & 1) {
      throw new Error('Unsafe ZIP member');
    }
    if (name === expectedName) {
      if (executable || ![0, 0x8000].includes(mode & 0xf000) || ![0, 8].includes(method)
          || expanded > 64 * 1024 * 1024) throw new Error('Invalid executable entry');
      bounds(bytes, localOffset, 30);
      if (bytes.readUInt32LE(localOffset) !== 0x04034b50
          || bytes.readUInt16LE(localOffset + 6) !== flags
          || bytes.readUInt16LE(localOffset + 8) !== method) throw new Error('Invalid ZIP local header');
      const localNameSize = bytes.readUInt16LE(localOffset + 26);
      const localExtraSize = bytes.readUInt16LE(localOffset + 28);
      bounds(bytes, localOffset + 30, localNameSize + localExtraSize + compressed);
      if (bytes.subarray(localOffset + 30, localOffset + 30 + localNameSize).toString('utf8') !== name) {
        throw new Error('ZIP local path mismatch');
      }
      const start = localOffset + 30 + localNameSize + localExtraSize;
      const content = bytes.subarray(start, start + compressed);
      executable = method === 0 ? content : inflateRawSync(content, { maxOutputLength: 64 * 1024 * 1024 });
      if (executable.length !== expanded) throw new Error('Invalid executable size');
    }
    cursor += 46 + nameSize + extraSize + commentSize;
  }
  if (!executable) throw new Error('Bootstrap executable missing');
  return executable;
}

async function download(spec) {
  const response = await fetch(spec.url, { redirect: 'error', signal: AbortSignal.timeout(120000) });
  if (!response.ok) throw new Error('Bootstrap download failed');
  const blocks = [];
  let length = 0;
  for await (const chunk of response.body) {
    length += chunk.length;
    if (length > spec.size) throw new Error('Bootstrap download exceeded its pinned size');
    blocks.push(chunk);
  }
  return verifyArtifact(Buffer.concat(blocks), spec);
}

function command(executable, args, env, timeout) {
  const result = spawnSync(executable, args, { env, timeout, encoding: 'utf8', windowsHide: true });
  if (result.status !== 0 || result.error) {
    const error = new Error('Managed Python bootstrap command failed');
    error.stage = args[0] === 'python' ? `python-${args[1]}` : 'python-execute';
    error.exitCode = result.status;
    throw error;
  }
  return result.stdout.trim();
}

export async function probeManagedPython() {
  const spec = BOOTSTRAPS[`${process.platform}-${process.arch}`];
  if (!spec) throw new Error('This platform has no verified bootstrap artifact');
  const started = performance.now();
  const root = await realpath(await mkdtemp(join(tmpdir(), 'qdrant-managed-python-')));
  const emptyPath = join(root, 'empty-path');
  await mkdir(emptyPath);
  const uv = join(root, process.platform === 'win32' ? 'uv.exe' : 'uv');
  const name = `uv-${UV_VERSION}.data/scripts/${process.platform === 'win32' ? 'uv.exe' : 'uv'}`;
  const executable = extractExecutable(await download(spec), name);
  await writeFile(uv, executable, { flag: 'wx', mode: 0o700 });
  const env = {
    PATH: emptyPath, UV_CACHE_DIR: join(root, 'cache'), UV_PYTHON_INSTALL_DIR: join(root, 'python'),
    UV_PYTHON_PREFERENCE: 'only-managed', UV_NO_CONFIG: '1',
  };
  for (const key of ['SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP']) {
    if (process.env[key]) env[key] = process.env[key];
  }
  command(uv, ['python', 'install', PYTHON_VERSION, '--no-bin'], env, 180000);
  const python = command(uv, ['python', 'find', PYTHON_VERSION], env, 10000);
  const inside = relative(root, python);
  if (!inside || inside.startsWith('..') || isAbsolute(inside)) throw new Error('Python escaped the fresh managed root');
  const version = command(python, ['-I', '-c', 'import sys; print(sys.version.split()[0])'], env, 10000);
  if (version !== PYTHON_VERSION) throw new Error('Unexpected Python version');
  return { platform: process.platform, architecture: process.arch, bootstrap_sha256_verified: true,
    system_tools_on_path: false, fresh_managed_python: true, python_version: version,
    elapsed_seconds: Number(((performance.now() - started) / 1000).toFixed(3)) };
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  if (process.argv.length !== 3 || process.argv[2] !== '--probe') {
    console.error('Usage: node integrations/managed/bootstrap.mjs --probe');
    process.exitCode = 2;
  } else {
    try { console.log(JSON.stringify(await probeManagedPython())); }
    catch (error) {
      console.error(JSON.stringify({ error: 'Managed Python probe failed; no memory profile was modified.',
        stage: error.stage || 'download-or-verification', exit_code: error.exitCode ?? null }));
      process.exitCode = 1;
    }
  }
}
