import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildRecallQuery, makeHybridRecallPrefetcher, normalizeRecallResults } from "./auto-recall.ts";
import { resolveEffectiveConfig } from "./config.ts";
import type { MemoryPromptBuilderCtx } from "./sdk-shim.ts";

const baseCtx: MemoryPromptBuilderCtx = {
  availableTools: new Set(["memory_search", "memory_get"]),
  citationsMode: "on",
  query: "What did we decide about billing retries?",
  threadId: "thread-123",
};

function makeBridge(response: unknown, fail = false): {
  bridge: { call: (method: string, params: Record<string, unknown>) => Promise<unknown> };
  calls: Array<{ method: string; params: Record<string, unknown> }>;
} {
  const calls: Array<{ method: string; params: Record<string, unknown> }> = [];
  return {
    calls,
    bridge: {
      call: async (method, params) => {
        calls.push({ method, params });
        if (fail) throw new Error("bridge failed");
        return response;
      },
    },
  };
}

describe("buildRecallQuery", () => {
  it("prefers explicit query", () => {
    assert.equal(buildRecallQuery({ ...baseCtx, latestUserMessage: "fallback" }), baseCtx.query);
  });

  it("falls back to recent user messages", () => {
    const query = buildRecallQuery({
      availableTools: new Set(),
      citationsMode: "auto",
      recentMessages: [
        { role: "assistant", content: "I can help." },
        { role: "user", content: "Remember that billing retries stop after 3 attempts." },
      ],
    });

    assert.equal(query, "Remember that billing retries stop after 3 attempts.");
  });
});

describe("normalizeRecallResults", () => {
  it("maps memory_search hits to prompt recall results", () => {
    const results = normalizeRecallResults({
      hits: [
        {
          path: "atom/atm_billing.md",
          layer: "atom",
          snippet: "Billing retries stop after the third attempt.",
          score: 0.92,
          source_id: "atm_billing",
          role_hint: "fact",
          occurred_at: "2026-06-16T00:00:00Z",
        },
      ],
    });

    assert.deepEqual(results, [
      {
        path: "atom/atm_billing.md",
        layer: "atom",
        title: undefined,
        snippet: "Billing retries stop after the third attempt.",
        score: 0.92,
        source_id: "atm_billing",
        metadata: {
          role_hint: "fact",
          occurred_at: "2026-06-16T00:00:00Z",
          total: undefined,
        },
      },
    ]);
  });
});

describe("makeHybridRecallPrefetcher", () => {
  it("calls memory_search only for hybrid mode", async () => {
    const cfg = resolveEffectiveConfig({ recall: { mode: "hybrid" } });
    const { bridge, calls } = makeBridge({
      hits: [{ path: "atom/atm_billing.md", snippet: "Retries stop after three attempts.", layer: "atom" }],
    });
    const prefetch = makeHybridRecallPrefetcher(cfg, async () => bridge);

    const results = await prefetch(baseCtx);

    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0], {
      method: "memory_search",
      params: {
        query: "What did we decide about billing retries?",
        maxResults: 5,
        corpus: "all",
        thread_id: "thread-123",
      },
    });
    assert.equal(results[0]?.path, "atom/atm_billing.md");
  });

  it("does not call memory_search for tool_hint mode", async () => {
    const cfg = resolveEffectiveConfig({ recall: { mode: "tool_hint" } });
    const { bridge, calls } = makeBridge({ hits: [] });
    const prefetch = makeHybridRecallPrefetcher(cfg, async () => bridge);

    assert.deepEqual(await prefetch(baseCtx), []);
    assert.equal(calls.length, 0);
  });

  it("reuses existing recallResults when host already prefetched", async () => {
    const cfg = resolveEffectiveConfig({ recall: { mode: "hybrid" } });
    const { bridge, calls } = makeBridge({ hits: [] });
    const prefetch = makeHybridRecallPrefetcher(cfg, async () => bridge);
    const existing = [{ path: "atom/existing.md", snippet: "Existing prefetch result." }];

    assert.deepEqual(await prefetch({ ...baseCtx, recallResults: existing }), existing);
    assert.equal(calls.length, 0);
  });

  it("returns empty results when no query is available", async () => {
    const cfg = resolveEffectiveConfig({ recall: { mode: "hybrid" } });
    const { bridge, calls } = makeBridge({ hits: [] });
    const prefetch = makeHybridRecallPrefetcher(cfg, async () => bridge);

    assert.deepEqual(await prefetch({ availableTools: new Set(), citationsMode: "auto" }), []);
    assert.equal(calls.length, 0);
  });

  it("warns and falls back to empty results when bridge fails", async () => {
    const warnings: unknown[][] = [];
    const cfg = resolveEffectiveConfig({ recall: { mode: "hybrid" } });
    const { bridge } = makeBridge({ hits: [] }, true);
    const prefetch = makeHybridRecallPrefetcher(cfg, async () => bridge, {
      warn: (...args) => warnings.push(args),
    });

    assert.deepEqual(await prefetch(baseCtx), []);
    assert.equal(warnings.length, 1);
  });
});
