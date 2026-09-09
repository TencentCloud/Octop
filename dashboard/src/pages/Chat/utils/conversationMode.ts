/** Conversation permission modes (#616): Ask / Plan / Craft. */

import type { TFunction } from "i18next";

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

/** Ant Design Select options shared by Experts create/edit drawers. */
export function conversationModeSelectOptions(
  t: TFunction,
): Array<{ value: ConversationMode; label: string }> {
  return [
    {
      value: "craft",
      label: t("chat.conversationModeCraft", "默认"),
    },
    {
      value: "plan",
      label: t("chat.conversationModePlan", "计划"),
    },
    {
      value: "ask",
      label: t("chat.conversationModeAsk", "问答"),
    },
  ];
}
