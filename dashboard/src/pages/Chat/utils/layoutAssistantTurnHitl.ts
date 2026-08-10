import type { ChatMessage } from "../hooks/useChat";

export interface AssistantTurnHitlSegment {
  /** Messages before this HITL card (tools / thinking). */
  processMessages: ChatMessage[];
  hitlMessage: ChatMessage;
}

export interface AssistantTurnHitlLayout {
  segments: AssistantTurnHitlSegment[];
  /** Messages after the last HITL (or all messages when none). */
  trailingMessages: ChatMessage[];
}

/**
 * Split an assistant turn around every HITL card so follow-up approvals
 * (after an earlier approve/reject) remain visible during live streaming.
 */
export function layoutAssistantTurnHitl(
  messages: ChatMessage[],
): AssistantTurnHitlLayout {
  const segments: AssistantTurnHitlSegment[] = [];
  let buf: ChatMessage[] = [];
  for (const m of messages) {
    if (m.hitlData) {
      segments.push({ processMessages: buf, hitlMessage: m });
      buf = [];
    } else {
      buf.push(m);
    }
  }
  return { segments, trailingMessages: buf };
}
