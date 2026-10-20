import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough } from "node:stream";
import test from "node:test";
import { ownerRequest } from "../integrations/pi/owner-memory.mjs";

test("Owner stdout preserves UTF-8 characters split between pipe chunks", async t => {
  const expected = { memories: [{ text: "中文記憶" }] };
  const bytes = Buffer.from(JSON.stringify(expected));
  const split = bytes.indexOf(Buffer.from("中")) + 1;
  t.mock.method(childProcess, "spawn", () => {
    const child = new EventEmitter();
    child.stdin = new PassThrough();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.kill = () => {};
    queueMicrotask(() => {
      child.stdout.write(bytes.subarray(0, split));
      child.stdout.end(bytes.subarray(split));
      child.emit("close", 0);
    });
    return child;
  });
  syncBuiltinESMExports();
  try {
    const result = await ownerRequest("remote-call", { query: "中文" }, {
      QDRANT_MEMORY_RUNTIME_PYTHON: "synthetic-runtime",
      QDRANT_MEMORY_OWNER_URL: "https://owner.test/mcp"
    });
    assert.deepEqual(result, expected);
  } finally { t.mock.restoreAll(); syncBuiltinESMExports(); }
});
