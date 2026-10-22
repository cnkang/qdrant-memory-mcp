import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { dirname, resolve } from "node:path";
import { PassThrough } from "node:stream";
import test from "node:test";
import { ownerRequest } from "../integrations/pi/owner-memory.mjs";

test("Owner stdout preserves UTF-8 characters split between pipe chunks", async t => {
  const expected = { memories: [{ text: "中文記憶" }] };
  const bytes = Buffer.from(JSON.stringify(expected));
  const split = bytes.indexOf(Buffer.from("中")) + 1;
  let spawned;
  t.mock.method(childProcess, "spawn", (...args) => {
    spawned = args;
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
      QDRANT_MEMORY_RUNTIME_PYTHON: resolve("synthetic-runtime"),
      QDRANT_MEMORY_OWNER_URL: "https://owner.test/mcp",
      QDRANT_MEMORY_CA_FILE: "ca.pem"
    });
    assert.deepEqual(result, expected);
    assert.deepEqual(spawned[1].slice(0, 3), ["-I", "-m", "qdrant_memory.standalone"]);
    assert.equal(spawned[0], resolve("synthetic-runtime"));
    assert.equal(spawned[1][spawned[1].indexOf("--ca-file") + 1], resolve(process.cwd(), "ca.pem"));
    assert.equal(spawned[2].cwd, dirname(resolve("synthetic-runtime")));
    assert.equal("PYTHONPATH" in spawned[2].env, false);
  } finally { t.mock.restoreAll(); syncBuiltinESMExports(); }
});

test("bare interpreter names are rejected before spawn", async () => {
  await assert.rejects(
    () => ownerRequest("remote-call", {}, {
      QDRANT_MEMORY_RUNTIME_PYTHON: "python3",
      QDRANT_MEMORY_OWNER_URL: "https://owner.test/mcp"
    }),
    /absolute path/
  );
});
