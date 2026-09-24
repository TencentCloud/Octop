/** Token counting via js-tiktoken/lite + cl100k_base ranks.
 *
 *  Uses the lite entrypoint (no full OpenAI bundle) plus a single ranks
 *  import so only the cl100k_base BPE table lands in the vendor-tiktoken
 *  chunk (~2 MB raw / ~700 KB gzipped). The encoder is loaded lazily on
 *  first use so the chat composer entry bundle stays small. */

import { Tiktoken } from "js-tiktoken/lite";
import ranksCl100k from "js-tiktoken/ranks/cl100k_base";
import type { TiktokenBPE } from "js-tiktoken";

let encoderPromise: Promise<Tiktoken> | null = null;

/** Lazy-load the cl100k_base encoder. The first call materialises the BPE
 *  table (~700 KB gzipped) into the vendor-tiktoken chunk; subsequent calls
 *  reuse the same instance. The promise is module-level so concurrent callers
 *  share a single load. */
function loadEncoder(): Promise<Tiktoken> {
  if (!encoderPromise) {
    encoderPromise = Promise.resolve(new Tiktoken(ranksCl100k as TiktokenBPE));
  }
  return encoderPromise;
}

/** Count BPE tokens in `text`. Returns 0 for empty input. */
export async function estimateTokens(text: string): Promise<number> {
  if (!text) return 0;
  const encoder = await loadEncoder();
  return encoder.encode(text).length;
}

/** Format a token count for the composer chip: "145", "1.2k", "23k".
 *  Keeps the chip narrow so it does not push the send button around. */
export function formatTokenCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n < 1_000) return String(n);
  if (n < 10_000) return `${(n / 1_000).toFixed(1)}k`;
  if (n < 1_000_000) return `${Math.round(n / 1_000)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

/** Test-only: reset the encoder cache so each test starts cold. */
export function __resetEstimateTokensForTest(): void {
  encoderPromise = null;
}