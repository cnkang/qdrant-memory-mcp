// Disposable test transport: publish child PID so acceptance can inject a crash.
import { spawn } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
const command = JSON.parse(process.env.QDRANT_TEST_CHILD);
const child = spawn(command.command, command.args, { env: command.env, stdio: ['pipe', 'pipe', 'ignore'] });
await writeFile(process.env.QDRANT_TEST_PID, String(child.pid));
process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
child.stdin.on('error', () => {});
process.on('SIGTERM', () => child.kill('SIGTERM'));
child.on('error', () => { process.exitCode = 1; process.stdin.destroy(); });
child.on('close', code => { process.exitCode = code ?? 1; process.stdin.destroy(); });
