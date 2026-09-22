import type { HitlPendingPayload } from "../api/types/hitl";
import type { ChatMessage } from "../pages/Chat/hooks/useChat";

export function injectPendingHitlMessage(
  messages: ChatMessage[],
  pending: HitlPendingPayload | null | undefined,
): ChatMessage[] {
  if (!pending?.action_requests?.length) return messages;
  const pendingId = pending.pending_id?.trim() || "";
  const injectedId = pendingId ? `hitl-${pendingId}` : "";
  if (
    messages.some(
      (m) =>
        m.hitlData?.status === "pending" ||
        (pendingId &&
          (m.id === injectedId || m.hitlData?.pending_id === pendingId)),
    )
  ) {
    return messages;
  }
  return [
    ...messages,
    {
      id: injectedId || `hitl-${Date.now()}`,
      role: "assistant",
      content: "",
      hitlData: {
        action_requests: pending.action_requests,
        review_configs: pending.review_configs,
        status: "pending",
        ...(pendingId ? { pending_id: pendingId } : {}),
      },
      status: "done",
      timestamp: Date.now(),
    },
  ];
}

export type { HitlPendingPayload };
