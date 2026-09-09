/** Conversation permission modes (#616): Ask / Plan / Craft. */

export type ConversationMode = "ask" | "plan" | "craft";

export const DEFAULT_CONVERSATION_MODE: ConversationMode = "craft";

const VALID: ReadonlySet<string> = new Set(["ask", "plan", "craft"]);

/** Composer options — default-first (WorkBuddy-style menu). */
export const COMPOSER_CONVERSATION_MODES: readonly ConversationMode[] = [
  "craft",
  "plan",
  "ask",
] as const;

export function parseConversationMode(
  value: unknown,
  fallback: ConversationMode = DEFAULT_CONVERSATION_MODE,
): ConversationMode {
  if (typeof value === "string" && VALID.has(value)) {
    return value as ConversationMode;
  }
  return fallback;
}
