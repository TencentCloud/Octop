// D52-C — flushPlanResolver for OpenClaw's compaction silent turn.
//
// Mirrors `extensions/memory-core/src/flush-plan.ts` (the official
// reference) but plumbs our config knobs (`compaction.*`) through.
//
// Sync + pure: the host calls this once per compaction event. We
// don't reach into the Python bridge here — there's no per-row state
// involved, just policy.

import type { MemoryFlushPlan, MemoryFlushPlanResolver, OpenClawConfig } from "./sdk-shim.js";

export const DEFAULT_SOFT_THRESHOLD_TOKENS = 4000;
export const DEFAULT_FORCE_FLUSH_TRANSCRIPT_BYTES = 2 * 1024 * 1024; // 2 MiB
export const DEFAULT_RESERVE_TOKENS_FLOOR = 2048;
export const SILENT_REPLY_TOKEN = "[silent]";

const TARGET_HINT =
  "Store durable memories only in memory/YYYY-MM-DD.md (create memory/ if needed).";
const APPEND_ONLY_HINT =
  "If memory/YYYY-MM-DD.md already exists, APPEND new content only and do not overwrite existing entries.";
const READ_ONLY_HINT =
  "Treat workspace bootstrap/reference files such as MEMORY.md, DREAMS.md, SOUL.md, TOOLS.md, and AGENTS.md as read-only during this flush; never overwrite, replace, or edit them.";

const DEFAULT_PROMPT = [
  "Pre-compaction memory flush.",
  TARGET_HINT,
  READ_ONLY_HINT,
  APPEND_ONLY_HINT,
  "Do NOT create timestamped variant files (e.g. YYYY-MM-DD-HHMM.md); always use the canonical YYYY-MM-DD.md filename.",
  `If nothing to store, reply with ${SILENT_REPLY_TOKEN}.`,
].join(" ");

const DEFAULT_SYSTEM_PROMPT = [
  "Pre-compaction memory flush turn.",
  "The session is near auto-compaction; capture durable memories to disk.",
  TARGET_HINT,
  READ_ONLY_HINT,
  APPEND_ONLY_HINT,
  `You may reply, but usually ${SILENT_REPLY_TOKEN} is correct.`,
].join(" ");

export interface BuildFlushPlanOptions {
  /** Plugin-level overrides (from `plugins.entries.octopmemory.config.compaction`). */
  pluginOverrides?: {
    enabled?: boolean;
    soft_threshold_tokens?: number;
    force_flush_transcript_bytes?: number;
    model?: string;
  };
}

export function makeFlushPlanResolver(
  options: BuildFlushPlanOptions = {},
): MemoryFlushPlanResolver {
  const overrides = options.pluginOverrides ?? {};

  return ({ cfg, nowMs }) => {
    if (overrides.enabled === false) {
      return null;
    }
    const hostFlush = cfg?.agents?.defaults?.compaction?.memoryFlush;
    if (hostFlush?.enabled === false) {
      return null;
    }

    const dateStamp = formatDate(nowMs ?? Date.now());

    const softThresholdTokens =
      normalizeInt(hostFlush?.softThresholdTokens) ??
      overrides.soft_threshold_tokens ??
      DEFAULT_SOFT_THRESHOLD_TOKENS;

    const forceFlushTranscriptBytes =
      normalizeInt(hostFlush?.forceFlushTranscriptBytes) ??
      overrides.force_flush_transcript_bytes ??
      DEFAULT_FORCE_FLUSH_TRANSCRIPT_BYTES;

    const reserveTokensFloor =
      normalizeInt(cfg?.agents?.defaults?.compaction?.reserveTokensFloor) ??
      DEFAULT_RESERVE_TOKENS_FLOOR;

    const promptText = ensureSafetyHints(hostFlush?.prompt?.trim() || DEFAULT_PROMPT);
    const systemPromptText = ensureSafetyHints(
      hostFlush?.systemPrompt?.trim() || DEFAULT_SYSTEM_PROMPT,
    );

    const plan: MemoryFlushPlan = {
      softThresholdTokens,
      forceFlushTranscriptBytes,
      reserveTokensFloor,
      model: hostFlush?.model?.trim() || overrides.model || undefined,
      prompt: promptText.replaceAll("YYYY-MM-DD", dateStamp),
      systemPrompt: systemPromptText.replaceAll("YYYY-MM-DD", dateStamp),
      relativePath: `memory/${dateStamp}.md`,
    };
    return plan;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(ms: number): string {
  const d = new Date(ms);
  const yyyy = d.getUTCFullYear().toString().padStart(4, "0");
  const mm = (d.getUTCMonth() + 1).toString().padStart(2, "0");
  const dd = d.getUTCDate().toString().padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function normalizeInt(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  const i = Math.floor(value);
  return i >= 0 ? i : undefined;
}

function ensureSafetyHints(text: string): string {
  let next = text.trim();
  for (const hint of [TARGET_HINT, APPEND_ONLY_HINT, READ_ONLY_HINT]) {
    if (!next.includes(hint)) {
      next = next ? `${next}\n\n${hint}` : hint;
    }
  }
  if (!next.includes(SILENT_REPLY_TOKEN)) {
    next = `${next}\n\nIf no user-visible reply is needed, start with ${SILENT_REPLY_TOKEN}.`;
  }
  return next;
}

// Re-export host config type so callers can hint the parameter cleanly.
export type { OpenClawConfig };
