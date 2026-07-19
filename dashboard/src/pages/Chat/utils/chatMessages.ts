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
  if (Array.isArray(raw.targetAgents) && raw.targetAgents.length > 0) {
    ctx.targetAgents = raw.targetAgents.map((s) => String(s));
    has = true;
  }
  if (typeof raw.model === "string" && raw.model.trim()) {
    ctx.model = raw.model.trim();
    has = true;
  }

  return has ? ctx : undefined;
}

/**
 * WS ``model`` field for each turn.
 *
 * A model explicitly selected in the composer wins; otherwise use the expert
 * default. Omit the field only when both are AUTO/empty.
 */
export function resolveTurnModelRef(
  selectedModel: string | null | undefined,
  agentDefaultModel: string | null | undefined,
): string | null {
  const selected = (selectedModel || "").trim();
  const agentDefault = (agentDefaultModel || "").trim();
  return selected || agentDefault || null;
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
  targetAgents?: string[];
  selectedModel?: string | null;
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
  if (params.targetAgents && params.targetAgents.length > 0) {
    ctx.targetAgents = [...params.targetAgents];
    has = true;
  }

  const selectedModel = (params.selectedModel || "").trim();
  if (selectedModel) {
    ctx.model = selectedModel;
    has = true;
  }

  return has ? ctx : undefined;
}

export function formatRunUsage(
  usage: TokenUsage | null | undefined,
  labels: { input: string; output: string; total: string },
): string | null {
  if (!usage) return null;

  const parts: string[] = [];
  if (typeof usage.input_tokens === "number") {
    parts.push(`${usage.input_tokens} ${labels.input}`);
  }
  if (typeof usage.output_tokens === "number") {
    parts.push(`${usage.output_tokens} ${labels.output}`);
  }
  if (typeof usage.total_tokens === "number") {
    parts.push(`${usage.total_tokens} ${labels.total}`);
  }
  return parts.length > 0 ? parts.join(" / ") : null;
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
