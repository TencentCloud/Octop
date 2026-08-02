import type { ChatMessage } from "./useChat";

/**
 * Mark every streaming *text/thinking* assistant bubble as done.
 * Call immediately before appending a *new* streaming bubble so prior text
 * does not keep `status: "streaming"` (and a blinking markdown caret).
 * Tool bubbles are left alone so parallel/in-flight tools stay "running".
 */
export function sealPriorStreamingAssistants(
  messages: ChatMessage[],
): ChatMessage[] {
  if (messages.length === 0) return messages;
  let changed = false;
  const next = messages.map((m) => {
    if (m.role === "assistant" && m.status === "streaming" && !m.toolData) {
      changed = true;
      return { ...m, status: "done" as const };
    }
    return m;
  });
  return changed ? next : messages;
}
