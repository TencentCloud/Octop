import type { BridgeClient } from "./bridge.js";
import type { EffectiveOctopMemoryConfig } from "./config.js";
import type {
  MemoryPromptBuilderCtx,
  MemoryPromptRecallResult,
  MemoryRecallPrefetcher,
} from "./sdk-shim.js";

const MAX_QUERY_CHARS = 1000;

type Logger = {
  warn?: (...args: unknown[]) => void;
};

type BridgeLike = Pick<BridgeClient, "call">;

interface MemorySearchHit {
  path?: unknown;
  layer?: unknown;
  title?: unknown;
  snippet?: unknown;
  excerpt?: unknown;
  text?: unknown;
  score?: unknown;
  source_id?: unknown;
  role_hint?: unknown;
  occurred_at?: unknown;
  [key: string]: unknown;
}

interface MemorySearchResponse {
  hits?: unknown;
  total?: unknown;
  empty_reason?: unknown;
}

export function makeHybridRecallPrefetcher(
  cfg: EffectiveOctopMemoryConfig,
  getBridge: () => Promise<BridgeLike>,
  logger?: Logger,
): MemoryRecallPrefetcher {
  return async (ctx: MemoryPromptBuilderCtx): Promise<MemoryPromptRecallResult[]> => {
    if (cfg.recall.mode !== "hybrid") {
      return [];
    }
    if (Array.isArray(ctx.recallResults) && ctx.recallResults.length > 0) {
      return ctx.recallResults;
    }

    const query = buildRecallQuery(ctx);
    if (!query) {
      return [];
    }

    try {
      const bridge = await getBridge();
      const response = (await bridge.call("memory_search", {
        query,
        maxResults: cfg.recall.default_max_results,
        corpus: cfg.recall.default_corpus,
        thread_id: ctx.threadId || ctx.sessionId || null,
      })) as MemorySearchResponse;
      return normalizeRecallResults(response);
    } catch (err) {
      logger?.warn?.("[octopmemory] hybrid auto-recall prefetch failed:", err);
      return [];
    }
  };
}

export function buildRecallQuery(ctx: MemoryPromptBuilderCtx): string | null {
  const explicit = cleanText(ctx.query || ctx.latestUserMessage || "");
  if (explicit) return truncateText(explicit, MAX_QUERY_CHARS);

  const recentUserMessages = (ctx.recentMessages ?? [])
    .filter((message) => message.role === undefined || message.role === "user")
    .map((message) => cleanText(message.content ?? ""))
    .filter((content) => content.length > 0);
  if (recentUserMessages.length === 0) {
    return null;
  }
  return truncateText(recentUserMessages.slice(-3).join("\n"), MAX_QUERY_CHARS);
}

export function normalizeRecallResults(response: MemorySearchResponse): MemoryPromptRecallResult[] {
  const hits = Array.isArray(response?.hits) ? response.hits : [];
  const out: MemoryPromptRecallResult[] = [];
  for (const hit of hits) {
    if (!isRecord(hit)) continue;
    const normalized = normalizeHit(hit as MemorySearchHit);
    if (normalized) out.push(normalized);
  }
  return out;
}

function normalizeHit(hit: MemorySearchHit): MemoryPromptRecallResult | null {
  const snippet = firstString(hit.snippet, hit.excerpt, hit.text);
  if (!snippet) return null;

  const path = toStringValue(hit.path);
  const sourceId = toStringValue(hit.source_id);
  return {
    path,
    layer: toStringValue(hit.layer),
    title: toStringValue(hit.title),
    snippet,
    score: toNumberValue(hit.score),
    source_id: sourceId,
    metadata: {
      role_hint: toStringValue(hit.role_hint),
      occurred_at: toStringValue(hit.occurred_at),
      total: toNumberValue(hit.total),
    },
  };
}

function firstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    const text = toStringValue(value);
    if (text) return text;
  }
  return undefined;
}

function toStringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function toNumberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function cleanText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function truncateText(value: string, maxChars: number): string {
  if (value.length <= maxChars) return value;
  if (maxChars <= 3) return value.slice(0, maxChars);
  return `${value.slice(0, maxChars - 3).trimEnd()}...`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
