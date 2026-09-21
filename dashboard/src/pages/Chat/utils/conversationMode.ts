export type ConversationMode = "ask" | "plan" | "craft";

export const DEFAULT_CONVERSATION_MODE: ConversationMode = "craft";

export function parseConversationMode(value: unknown): ConversationMode {
  if (value === "ask" || value === "plan" || value === "craft") return value;
  return DEFAULT_CONVERSATION_MODE;
}

export function isRestrictedConversationMode(mode: ConversationMode): boolean {
  return mode === "ask" || mode === "plan";
}
