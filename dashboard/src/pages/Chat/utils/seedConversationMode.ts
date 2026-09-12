import { isPendingThread } from "../hooks/useSessions";
import {
  parseConversationMode,
  type ConversationMode,
} from "./conversationMode";

export type SeedConversationModeResult =
  | { action: "set"; mode: ConversationMode }
  | { action: "stamp-override"; mode: ConversationMode }
  | { action: "keep" };

/**
 * Decide how the composer conversation mode should react when the active
 * thread id (or agent default) changes.
 *
 * Critical path: empty / pending chat → first real thread id must **stamp**
 * the mode the user already picked, not wipe back to the agent default.
 * Otherwise a Plan first-send never shows PlanReady.
 */
export function resolveSeedConversationMode(params: {
  activeThreadId?: string | null;
  previousThreadId?: string | null;
  override?: ConversationMode;
  agentDefault?: ConversationMode | string | null;
  currentComposerMode: ConversationMode;
}): SeedConversationModeResult {
  const {
    activeThreadId,
    previousThreadId,
    override,
    agentDefault,
    currentComposerMode,
  } = params;

  if (!activeThreadId) {
    return { action: "set", mode: parseConversationMode(agentDefault) };
  }

  // `__pending__` is reused for every new chat. Never restore a stale override
  // from a previous first-send — always stamp the composer mode the user has
  // now. Same when empty composer first receives a real thread id.
  const fromEmptyComposer =
    previousThreadId == null ||
    previousThreadId === "" ||
    isPendingThread(previousThreadId) ||
    isPendingThread(activeThreadId);
  if (fromEmptyComposer) {
    return { action: "stamp-override", mode: currentComposerMode };
  }

  if (override !== undefined) {
    return { action: "set", mode: override };
  }

  return { action: "set", mode: parseConversationMode(agentDefault) };
}
