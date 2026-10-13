import {
  normalizeHitlRequest,
  type HitlPendingPayload,
} from "../api/types/hitl";
import type { ChatMessage } from "../pages/Chat/hooks/useChat";

function asPendingPayload(raw: unknown): HitlPendingPayload | null {
  const normalized = normalizeHitlRequest(raw);
  const actionRequests = normalized.action_requests;
  if (!Array.isArray(actionRequests) || actionRequests.length === 0) {
    return null;
  }
  return {
    action_requests: actionRequests as HitlPendingPayload["action_requests"],
    review_configs: Array.isArray(normalized.review_configs)
      ? (normalized.review_configs as HitlPendingPayload["review_configs"])
      : undefined,
    pending_id:
      typeof normalized.pending_id === "string"
        ? normalized.pending_id
        : undefined,
  };
}

export function injectPendingHitlMessage(
  messages: ChatMessage[],
  pending: HitlPendingPayload | null | undefined,
): ChatMessage[] {
  const normalized = pending ? asPendingPayload(pending) : null;
  if (!normalized?.action_requests?.length) return messages;
  const pendingId = normalized.pending_id?.trim() || "";
  const injectedId = pendingId ? `hitl-${pendingId}` : "";
  if (
    pendingId &&
    messages.some(
      (m) => m.id === injectedId || m.hitlData?.pending_id === pendingId,
    )
  ) {
    return messages;
  }
  const reconstructedIdx = messages.findIndex(
    (m) => m.hitlData?.status === "pending" && !m.hitlData.pending_id,
  );
  if (reconstructedIdx >= 0) {
    const current = messages[reconstructedIdx];
    const next = [...messages];
    next[reconstructedIdx] = {
      ...current,
      id: injectedId || current.id,
      hitlData: {
        ...current.hitlData,
        action_requests: normalized.action_requests,
        review_configs: normalized.review_configs,
        status: "pending",
        ...(pendingId ? { pending_id: pendingId } : {}),
      },
    };
    return next;
  }
  if (messages.some((m) => m.hitlData?.status === "pending")) {
    return messages;
  }
  return [
    ...messages,
    {
      id: injectedId || `hitl-${Date.now()}`,
      role: "assistant",
      content: "",
      hitlData: {
        action_requests: normalized.action_requests,
        review_configs: normalized.review_configs,
        status: "pending",
        ...(pendingId ? { pending_id: pendingId } : {}),
      },
      status: "done",
      timestamp: Date.now(),
    },
  ];
}

export type { HitlPendingPayload };
