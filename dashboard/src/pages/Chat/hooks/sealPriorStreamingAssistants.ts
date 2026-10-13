import { sameStreamingSpeaker } from "../utils/messageGrouping";
import type { ChatMessage } from "./useChat";

/**
 * Mark streaming *text/thinking* assistant bubbles as done.
 * Call immediately before appending a *new* streaming bubble so prior text
 * does not keep `status: "streaming"` (and a blinking markdown caret).
 * Tool bubbles are left alone so parallel/in-flight tools stay "running".
 *
 * When *speakerId* is set, only that speaker is sealed so a team member can
 * stream beside the host without killing the host caret.
 */
export function sealPriorStreamingAssistants(
  messages: ChatMessage[],
  speakerId?: string,
  hostAgentId?: string,
  teamRoom = false,
): ChatMessage[] {
  if (messages.length === 0) return messages;
  let changed = false;
  const next = messages.map((m) => {
    if (m.role === "assistant" && m.status === "streaming" && !m.toolData) {
      if (
        !sameStreamingSpeaker(
          m.speakerAgentId,
          speakerId,
          hostAgentId,
          teamRoom,
        )
      )
        return m;
      changed = true;
      return { ...m, status: "done" as const };
    }
    return m;
  });
  return changed ? next : messages;
}
