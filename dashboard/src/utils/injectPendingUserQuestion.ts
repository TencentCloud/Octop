import type { UserQuestionPendingPayload } from "../api/types/userQuestions";
import type { ChatMessage } from "../pages/Chat/hooks/useChat";

export function injectPendingUserQuestion(
  messages: ChatMessage[],
  pending: UserQuestionPendingPayload | null | undefined,
): ChatMessage[] {
  if (!pending?.pending_id || !pending.questions?.length) return messages;
  if (messages.some((message) => message.questionData?.status === "pending")) {
    return messages;
  }
  return [
    ...messages,
    {
      id: `question-${pending.pending_id}`,
      role: "assistant",
      content: "",
      questionData: {
        pendingId: pending.pending_id,
        questions: pending.questions,
        status: "pending",
      },
      status: "done",
      timestamp: Date.now(),
    },
  ];
}
