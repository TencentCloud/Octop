// D51-C / D52-C — prompt section builder.
//
// Mirrors `extensions/memory-core/src/prompt-section.ts` but with our
// brand + tool names. OpenClaw's current promptBuilder contract is
// synchronous, so this module deliberately does NOT call the Python
// bridge. Actual recall content normally flows through `memory_search` /
// `memory_get`; when future hosts prefetch recall results before prompt
// build, this builder can render those results into the hybrid prompt
// section.

import type { RecallMode } from "./config.js";
import type {
  CitationsMode,
  MemoryPromptBuilderCtx,
  MemoryPromptRecallResult,
  MemoryPromptSectionBuilder,
} from "./sdk-shim.js";

export interface PromptSectionConfig {
  mode?: RecallMode;
  maxPromptChars?: number;
}

export const DEFAULT_RECALL_MODE: RecallMode = "tool_hint";
const DEFAULT_MAX_PROMPT_CHARS = 1200;
const MAX_QUERY_CHARS = 500;
const MAX_SNIPPET_CHARS = 320;

export const buildPromptSection: MemoryPromptSectionBuilder = makePromptSectionBuilder();

export function makePromptSectionBuilder(config: PromptSectionConfig = {}): MemoryPromptSectionBuilder {
  const mode = config.mode ?? DEFAULT_RECALL_MODE;
  const maxPromptChars = config.maxPromptChars ?? DEFAULT_MAX_PROMPT_CHARS;

  return (ctx: MemoryPromptBuilderCtx): string[] => {
    const { availableTools, citationsMode } = ctx;
    if (mode === "off") {
      return [];
    }

    const hasSearch = availableTools.has("memory_search");
    const hasGet = availableTools.has("memory_get");

    if (!hasSearch && !hasGet) {
      return [];
    }

    const toolGuidance = pickToolGuidance(hasSearch, hasGet, mode, ctx);

    const lines: string[] = ["## Memory Recall", toolGuidance];
    if (mode === "hybrid") {
      lines.push(...renderQueryContext(ctx));
      lines.push(...renderPrefetchedRecall(ctx.recallResults, maxPromptChars));
    }

    // Citation rendering policy. `off` means the host wants NO file/line
    // refs in user-facing replies; otherwise we suggest `Source:` lines
    // so the user can verify the claim against the underlying virtual
    // path (atom/<id>.md, page/<id>.md, raw/<date>/<id>.md, or a
    // host-written memory/<date>.md).
    if (citationsMode === "off") {
      lines.push(
        "Citations are disabled: do not mention memory paths or line numbers in replies unless the user explicitly asks.",
      );
    } else {
      lines.push(
        "Citations: include `Source: <path>` (e.g. `Source: atom/atm_a3f2c891.md`) when it helps the user verify a recalled fact.",
      );
    }

    // Layered recall hint — octopmemory-specific. Entity pages are
    // readable by a known path, but are not currently searched by
    // memory_search.
    lines.push(
      "Layers: `atom/*.md` are vetted facts (highest precision); raw results are unfiltered transcripts; host memory files preserve host-written notes. `page/<entity>.md` summaries are readable when you already know the path, but are not currently a search source.",
    );

    lines.push("");
    return lines;
  };
}

function pickToolGuidance(hasSearch: boolean, hasGet: boolean, mode: RecallMode, ctx: MemoryPromptBuilderCtx): string {
  const prefix = mode === "hybrid" ? hybridGuidancePrefix(ctx) : "";

  if (hasSearch && hasGet) {
    return (
      prefix +
      "Use `memory_search` before answering anything about prior decisions, people, preferences, todos, or recent work; " +
      "then use `memory_get` to pull the exact lines you need. If still unsure, say so explicitly rather than guessing."
    );
  }
  if (hasSearch) {
    return (
      prefix +
      "Use `memory_search` before answering anything about prior decisions, people, preferences, todos, or recent work; " +
      "answer from the matching results. If still unsure, say so explicitly."
    );
  }
  // memory_get only — already know the path. Rare case.
  return (
    prefix +
    "When you already know a memory path (e.g. `atom/atm_a3f2c891.md`), use `memory_get` to read " +
    "the exact lines. If still unsure after reading, say so explicitly."
  );
}

function hybridGuidancePrefix(ctx: MemoryPromptBuilderCtx): string {
  if (Array.isArray(ctx.recallResults) && ctx.recallResults.length > 0) {
    return "Hybrid auto-recall has preloaded relevant memories below. ";
  }
  if (ctx.query || ctx.latestUserMessage) {
    return "Hybrid auto-recall is configured for the query context below. ";
  }
  return "Hybrid auto-recall is configured, but this prompt context has no user query to prefetch from. ";
}

function renderQueryContext(ctx: MemoryPromptBuilderCtx): string[] {
  const query = cleanInline(ctx.query || ctx.latestUserMessage || "", MAX_QUERY_CHARS);
  const scopeCandidates: Array<[string, string | undefined]> = [
    ["thread_id", ctx.threadId],
    ["session_id", ctx.sessionId],
    ["user_id", ctx.userId],
    ["agent_id", ctx.agentId],
  ];
  const scopeParts = scopeCandidates
    .filter((item): item is [string, string] => typeof item[1] === "string" && item[1].trim().length > 0)
    .map(([key, value]) => `${key}=${cleanInline(value, 120)}`);

  const lines: string[] = [];
  if (query) {
    lines.push(`Query context: ${query}`);
  }
  if (scopeParts.length > 0) {
    lines.push(`Scope: ${scopeParts.join(", ")}`);
  }
  return lines;
}

function renderPrefetchedRecall(
  recallResults: MemoryPromptRecallResult[] | undefined,
  maxPromptChars: number,
): string[] {
  if (!Array.isArray(recallResults) || recallResults.length === 0 || maxPromptChars <= 0) {
    return [];
  }

  const lines: string[] = ["Relevant memories:"];
  let used = 0;
  for (const result of recallResults) {
    const line = renderRecallResult(result);
    if (!line) continue;
    const lineCost = line.length + 1;
    if (used > 0 && used + lineCost > maxPromptChars) {
      lines.push("- ...additional memories omitted by recall.max_prompt_chars budget.");
      break;
    }
    if (used === 0 && lineCost > maxPromptChars) {
      lines.push(truncateText(line, Math.max(0, maxPromptChars - 1)));
      break;
    }
    lines.push(line);
    used += lineCost;
  }

  return lines.length > 1 ? lines : [];
}

function renderRecallResult(result: MemoryPromptRecallResult): string | null {
  const text = cleanInline(result.snippet || result.excerpt || result.text || "", MAX_SNIPPET_CHARS);
  if (!text) return null;

  const prefix = result.title ? `${cleanInline(result.title, 120)}: ` : "";
  const source = result.path || result.source_id;
  const suffix = source ? ` (Source: ${cleanInline(source, 180)})` : "";
  return `- ${prefix}${text}${suffix}`;
}

function cleanInline(value: string, maxChars: number): string {
  return truncateText(value.replace(/\s+/g, " ").replace(/`/g, "'").trim(), maxChars);
}

function truncateText(value: string, maxChars: number): string {
  if (maxChars <= 0) return "";
  if (value.length <= maxChars) return value;
  if (maxChars <= 3) return value.slice(0, maxChars);
  return `${value.slice(0, maxChars - 3).trimEnd()}...`;
}

// Re-export the citations mode literal so callers can pass it cleanly
// without importing from the sdk-shim path.
export type { CitationsMode };
