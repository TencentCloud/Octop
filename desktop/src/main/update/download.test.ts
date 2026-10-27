import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { downloadToFile, type FetchLike } from "./download";

async function withTempDir(fn: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(join(tmpdir(), "octop-dl-"));
  try {
    await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function bodyOf(chunks: string[], headers: Record<string, string> = {}): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers });
}

test("downloadToFile streams to disk and reports progress", async () => {
  await withTempDir(async (dir) => {
    const dest = join(dir, "Octop.dmg");
    const seen: number[] = [];
    const fetchImpl: FetchLike = async () => bodyOf(["abc", "defg"]);
    await downloadToFile("https://download.octop.cloud/Octop.dmg", dest, fetchImpl, {
      onProgress: (received, total) => seen.push(total === 0 ? received : total),
    });
    assert.equal(await readFile(dest, "utf8"), "abcdefg");
    // Two chunks were written; no content-length means total stays 0.
    assert.deepEqual(seen, [3, 7]);
  });
});

test("downloadToFile reports content-length as the total", async () => {
  await withTempDir(async (dir) => {
    const dest = join(dir, "Octop.dmg");
    const total = 7;
    const fetchImpl: FetchLike = async () =>
      bodyOf(["abc", "defg"], { "content-length": String(total) });
    const seen: number[] = [];
    await downloadToFile("https://download.octop.cloud/Octop.dmg", dest, fetchImpl, {
      onProgress: (_received, receivedTotal) => seen.push(receivedTotal),
    });
    assert.deepEqual(seen, [total, total]);
  });
});

test("downloadToFile rejects a non-2xx response and leaves no file", async () => {
  await withTempDir(async (dir) => {
    const dest = join(dir, "Octop.dmg");
    const fetchImpl: FetchLike = async () => new Response("nope", { status: 502 });
    await assert.rejects(
      downloadToFile("https://download.octop.cloud/Octop.dmg", dest, fetchImpl),
      /HTTP 502/,
    );
    await assert.rejects(stat(dest));
  });
});

test("downloadToFile removes a partial file when the body fails mid-stream", async () => {
  await withTempDir(async (dir) => {
    const dest = join(dir, "Octop.dmg");
    const fetchImpl: FetchLike = async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode("partial"));
            controller.error(new Error("connection reset"));
          },
        }),
        { status: 200 },
      );
    await assert.rejects(
      downloadToFile("https://download.octop.cloud/Octop.dmg", dest, fetchImpl),
      /connection reset/,
    );
    await assert.rejects(stat(dest));
  });
});
