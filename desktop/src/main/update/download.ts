/**
 * Streaming download for a shell update package (§6.3). The response body is
 * piped straight to disk so a 100+ MB installer never sits in memory, and a
 * failed transfer leaves no partial file behind.
 */

import { createWriteStream } from "node:fs";
import { rm } from "node:fs/promises";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";

/** Minimal shape of Electron's ``net.fetch`` / Node's global ``fetch``. */
export type FetchLike = (
  url: string,
  init?: { cache?: "no-store"; headers?: Record<string, string> },
) => Promise<Response>;

export interface DownloadOptions {
  /** ``total`` is 0 when the server omits content-length. */
  onProgress?: (received: number, total: number) => void;
}

export async function downloadToFile(
  url: string,
  destPath: string,
  fetchImpl: FetchLike,
  options: DownloadOptions = {},
): Promise<void> {
  const res = await fetchImpl(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`下载失败：HTTP ${res.status}`);
  if (!res.body) throw new Error("下载失败：响应没有内容");

  const total = Number(res.headers.get("content-length") ?? 0) || 0;
  let received = 0;
  const counter = new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      received += chunk.length;
      options.onProgress?.(received, total);
      callback(null, chunk);
    },
  });

  try {
    await pipeline(
      Readable.fromWeb(res.body as unknown as import("node:stream/web").ReadableStream<Uint8Array>),
      counter,
      createWriteStream(destPath),
    );
  } catch (err) {
    await rm(destPath, { force: true }).catch(() => undefined);
    throw err;
  }
}
