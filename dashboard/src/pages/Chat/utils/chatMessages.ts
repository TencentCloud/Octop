import type { TokenUsage } from "../../../api/types";
import { generateId } from "../../../utils/messageParser";
import type {
  ChatAttachment,
  ChatMessage,
  UserComposerContext,
} from "../hooks/sseHelpers";

export function normalizeComposerContext(
  value: unknown,
): UserComposerContext | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const raw = value as Record<string, unknown>;
  const ctx: UserComposerContext = {};
  let has = false;

  if (Array.isArray(raw.skills) && raw.skills.length > 0) {
    ctx.skills = raw.skills.map((s) => String(s));
    has = true;
  }
  if (Array.isArray(raw.connectors) && raw.connectors.length > 0) {
    ctx.connectors = raw.connectors.map((s) => String(s));
    has = true;
  }
  if (Array.isArray(raw.knowledgeBaseIds) && raw.knowledgeBaseIds.length > 0) {
    ctx.knowledgeBaseIds = raw.knowledgeBaseIds.map((id) => String(id));
    has = true;
  }
  if (Array.isArray(raw.targetAgents) && raw.targetAgents.length > 0) {
    ctx.targetAgents = raw.targetAgents.map((s) => String(s));
    has = true;
  }
  if (typeof raw.model === "string" && raw.model.trim()) {
    ctx.model = raw.model.trim();
    has = true;
  }
  if (
    raw.reasoningMode === "auto" ||
    raw.reasoningMode === "enabled" ||
    raw.reasoningMode === "disabled"
  ) {
    ctx.reasoningMode = raw.reasoningMode;
    has = true;
  }
  if (typeof raw.reasoningEffort === "string" && raw.reasoningEffort.trim()) {
    ctx.reasoningEffort = raw.reasoningEffort.trim();
    has = true;
  }

  return has ? ctx : undefined;
}

/**
 * WS ``model`` field for each turn.
 *
 * Only an explicit composer selection is sent. Agent/user/global defaults are
 * resolved by the backend so they are not mistaken for a sticky override.
 */
export function resolveTurnModelRef(
  selectedModel: string | null | undefined,
  agentDefaultModel: string | null | undefined,
): string | null {
  const selected = (selectedModel || "").trim();
  void agentDefaultModel;
  return selected || null;
}

/** User picked a model different from the expert default (for UI chips / history). */
export function resolveTurnModelOverride(
  selectedModel: string | null | undefined,
  agentDefaultModel: string | null | undefined,
): string | null {
  const selected = (selectedModel || "").trim();
  const agentDefault = (agentDefaultModel || "").trim();
  if (!selected || (agentDefault && selected === agentDefault)) {
    return null;
  }
  return selected;
}

export function buildComposerContext(params: {
  skills?: string[];
  connectors?: string[];
  knowledgeBaseIds?: string[];
  targetAgents?: string[];
  selectedModel?: string | null;
  reasoningMode?: "auto" | "enabled" | "disabled";
  reasoningEffort?: string | null;
}): UserComposerContext | undefined {
  const ctx: UserComposerContext = {};
  let has = false;

  if (params.skills && params.skills.length > 0) {
    ctx.skills = [...params.skills];
    has = true;
  }
  if (params.connectors && params.connectors.length > 0) {
    ctx.connectors = [...params.connectors];
    has = true;
  }
  if (params.knowledgeBaseIds && params.knowledgeBaseIds.length > 0) {
    ctx.knowledgeBaseIds = [...params.knowledgeBaseIds];
    has = true;
  }
  if (params.targetAgents && params.targetAgents.length > 0) {
    ctx.targetAgents = [...params.targetAgents];
    has = true;
  }

  const selectedModel = (params.selectedModel || "").trim();
  if (selectedModel) {
    ctx.model = selectedModel;
    has = true;
  }
  if (params.reasoningMode) {
    ctx.reasoningMode = params.reasoningMode;
    has = true;
  }
  if (params.reasoningEffort) {
    ctx.reasoningEffort = params.reasoningEffort;
    has = true;
  }

  return has ? ctx : undefined;
}

export function formatRunUsage(
  usage: TokenUsage | null | undefined,
  labels: { input: string; output: string; total: string; cacheHit: string },
): string | null {
  if (!usage) return null;

  const parts: string[] = [];
  if (typeof usage.input_tokens === "number") {
    parts.push(`${usage.input_tokens} ${labels.input}`);
  }
  if (
    typeof usage.cache_read_tokens === "number" &&
    usage.cache_read_tokens > 0
  ) {
    const percent =
      typeof usage.input_tokens === "number" && usage.input_tokens > 0
        ? ` (${Math.round(
            (usage.cache_read_tokens / usage.input_tokens) * 100,
          )}%)`
        : "";
    parts.push(`${usage.cache_read_tokens} ${labels.cacheHit}${percent}`);
  }
  if (typeof usage.output_tokens === "number") {
    parts.push(`${usage.output_tokens} ${labels.output}`);
  }
  if (typeof usage.total_tokens === "number") {
    parts.push(`${usage.total_tokens} ${labels.total}`);
  }
  return parts.length > 0 ? parts.join(" / ") : null;
}

/** Count user turns from *messageId* through the latest (inclusive). */
export function userTurnsFromEnd(
  messages: Array<{ id: string; role: string }>,
  messageId: string,
): number {
  const idx = messages.findIndex((message) => message.id === messageId);
  if (idx < 0) return 0;
  return messages.slice(idx).filter((message) => message.role === "user")
    .length;
}

/** Count assistant answer turns from *messageId* through the latest (inclusive). */
export function assistantTurnsFromEnd(
  messages: Array<{ id: string; role: string; toolData?: unknown }>,
  messageId: string,
): number {
  const idx = messages.findIndex((message) => message.id === messageId);
  if (idx < 0) return 0;
  return messages
    .slice(idx)
    .filter((message) => message.role === "assistant" && !message.toolData)
    .length;
}

export function buildUserMessage(
  text: string,
  attachments?: ChatAttachment[],
  composerContext?: UserComposerContext,
): ChatMessage {
  return {
    id: generateId(),
    role: "user",
    content: text,
    attachments:
      attachments && attachments.length > 0 ? attachments : undefined,
    composerContext,
    status: "done",
    timestamp: Date.now(),
  };
}
