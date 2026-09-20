import {
  extractAskQuestions,
  isAskHitl,
  type AskQuestion,
} from "../../../api/types/hitl";
import type { ChatMessage, HitlActionRequest } from "../hooks/sseHelpers";

export type PendingAsk = {
  messageId: string;
  actions: HitlActionRequest[];
  questions: AskQuestion[];
};

/** True when any message still awaits a HITL decision. */
export function hasPendingHitl(messages: ChatMessage[]): boolean {
  return messages.some((message) => message.hitlData?.status === "pending");
}

/** Latest pending ``ask_user_question`` card, if any. */
export function findPendingAsk(messages: ChatMessage[]): PendingAsk | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    const hitl = message.hitlData;
    if (
      !hitl ||
      (hitl.status ?? "pending") !== "pending" ||
      !isAskHitl(hitl.action_requests)
    ) {
      continue;
    }
    const questions = extractAskQuestions(hitl.action_requests);
    if (questions.length > 0) {
      return {
        messageId: message.id,
        actions: hitl.action_requests,
        questions,
      };
    }
  }
  return null;
}
