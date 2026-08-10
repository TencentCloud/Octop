import type { HitlPendingPayload } from "../api/types/hitl";
import type { ChatMessage } from "../pages/Chat/hooks/useChat";

export function injectPendingHitlMessage(
  messages: ChatMessage[],
  pending: HitlPendingPayload | null | undefined,
): ChatMessage[] {
  if (!pending?.action_requests?.length) return messages;
  if (messages.some((m) => m.hitlData?.status === "pending")) return messages;
  return [
    ...messages,
    {
      id: pending.pending_id
        ? `hitl-${pending.pending_id}`
        : `hitl-${Date.now()}`,
      role: "assistant",
      content: "",
      hitlData: {
        action_requests: pending.action_requests,
        review_configs: pending.review_configs,
        status: "pending",
      },
      status: "done",
      timestamp: Date.now(),
    },
  ];
}

export type { HitlPendingPayload };
