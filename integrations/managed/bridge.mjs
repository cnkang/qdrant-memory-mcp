/** Small stdio readiness boundary; Runtime remains the only tool implementation. */
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { readFile } from 'node:fs/promises';
import { isDeepStrictEqual } from 'node:util';

export const tools = JSON.parse(await readFile(new URL('./tools.json', import.meta.url), 'utf8'));
const failure = text => ({ content: [{ type: 'text', text }], isError: true });

export async function bridge(startBackend, input = process.stdin, output = process.stdout) {
  const abort = new AbortController();
  const pending = new Map();
  let backend, ready = false, closed = false, sequence = 0, initialized = false;
  let state = 'Preparing memory. No operation was performed; retry when preparation finishes.';
  const send = message => { if (!closed) output.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n'); };
  const wire = message => backend.stdin.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n');
  let finish;
  const done = new Promise(resolve => { finish = resolve; });
  const shutdown = () => {
    if (closed) return;
    closed = true;
    abort.abort();
    if (backend && backend.exitCode === null && backend.signalCode === null) {
      backend.stdin.end();
      // Allow Runtime to close storage/lease normally before SDK-style escalation.
      const term = setTimeout(() => backend.kill('SIGTERM'), 3000);
      const kill = setTimeout(() => backend.kill('SIGKILL'), 6000);
      backend.once('close', () => { clearTimeout(term); clearTimeout(kill); });
    }
    finish();
  };
  const lines = createInterface({ input, crlfDelay: Infinity });
  const onSignal = () => { lines.close(); shutdown(); };
  process.once('SIGTERM', onSignal);
  process.once('SIGINT', onSignal);
  lines.on('close', shutdown);
  lines.on('line', line => {
    if (closed) return;
    let message;
    try { message = JSON.parse(line); } catch { send({ id: null, error: { code: -32700, message: 'Parse error' } }); return; }
    if (!message || typeof message !== 'object' || Array.isArray(message) || message.jsonrpc !== '2.0') {
      send({ id: null, error: { code: -32600, message: 'Invalid request' } }); return;
    }
    const hasId = Object.hasOwn(message, 'id');
    if (!hasId) {
      if (ready && message.method === 'notifications/cancelled') {
        const entry = [...pending].find(([, id]) => id === message.params?.requestId);
        if (entry) wire({ method: message.method, params: { ...message.params, requestId: entry[0] } });
      }
      return;
    }
    const { id, method } = message;
    if (method === 'initialize') {
      initialized = true;
      const version = message.params?.protocolVersion;
      send({ id, result: { protocolVersion: ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'].includes(version) ? version : '2025-11-25',
        capabilities: { tools: {} }, serverInfo: { name: 'qdrant-memory-managed', version: '0.1.0' } } });
    } else if (method === 'ping') send({ id, result: {} });
    else if (!initialized) send({ id, error: { code: -32000, message: 'Initialize first' } });
    else if (method === 'tools/list') send({ id, result: { tools } });
    else if (method === 'tools/call') {
      if (!ready) send({ id, result: failure(state) });
      else {
        const internal = ++sequence;
        pending.set(internal, id);
        wire({ id: internal, method, params: message.params });
      }
    } else send({ id, error: { code: -32601, message: 'Method not found' } });
  });
  void (async () => {
    try {
      const command = await startBackend(abort.signal);
      if (closed) return;
      backend = spawn(command.command, command.args, { env: command.env, windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'] });
      const failed = () => {
        ready = false;
        state = 'Memory backend stopped. No automatic write retry was performed; reconnect and search before retrying a write.';
        for (const id of pending.values()) send({ id, result: failure(state) });
        pending.clear();
        // Closing the transport lets the host's own reconnect/backoff policy act.
        // Never leave a live bridge that masks a dead Runtime indefinitely.
        lines.close();
        shutdown();
      };
      backend.on('error', failed);
      backend.on('close', failed);
      backend.stdin.on('error', failed);
      const responses = createInterface({ input: backend.stdout, crlfDelay: Infinity });
      responses.on('line', line => {
        let message;
        try { message = JSON.parse(line); } catch { failed(); backend.kill(); return; }
        if (message.id === 'init') {
          if (!message.result) { failed(); return; }
          wire({ method: 'notifications/initialized' });
          wire({ id: 'catalogue', method: 'tools/list', params: {} });
        } else if (message.id === 'catalogue') {
          if (!isDeepStrictEqual(message.result?.tools, tools)) { failed(); backend.kill(); return; }
          ready = true;
        } else if (pending.has(message.id)) {
          const id = pending.get(message.id);
          pending.delete(message.id);
          send({ ...message, id });
        }
      });
      backend.once('spawn', () => wire({ id: 'init', method: 'initialize', params: {
        protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'managed-launcher', version: '0.1.0' } } }));
    } catch {
      state = 'Memory preparation failed. No operation was performed. Run the launcher prepare command to retry; inspect network and disk access.';
    }
  })();
  await done;
  process.removeListener('SIGTERM', onSignal);
  process.removeListener('SIGINT', onSignal);
}
