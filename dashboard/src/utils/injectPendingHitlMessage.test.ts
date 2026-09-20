import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../pages/Chat/hooks/useChat";
import { injectPendingHitlMessage } from "./injectPendingHitlMessage";

function msg(
  partial: Partial<ChatMessage> & Pick<ChatMessage, "id" | "role">,
): ChatMessage {
  return {
    content: "",
    status: "done",
    timestamp: 0,
    ...partial,
  };
}

const pending = {
  pending_id: "ab12",
  action_requests: [{ name: "ask_user_question", args: { questions: [] } }],
};

describe("injectPendingHitlMessage", () => {
  it("appends one pending card when history has none", () => {
    const out = injectPendingHitlMessage([], pending);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe("hitl-ab12");
    expect(out[0].hitlData?.status).toBe("pending");
    expect(out[0].hitlData?.pending_id).toBe("ab12");
  });

  it("does not append a second card after the first was answered", () => {
    const answered = [
      msg({
        id: "hitl-ab12",
        role: "assistant",
        hitlData: {
          action_requests: pending.action_requests,
          status: "approved",
          pending_id: "ab12",
        },
      }),
    ];
    expect(injectPendingHitlMessage(answered, pending)).toEqual(answered);
  });

  it("does not append when a pending card is already in the list", () => {
    const existing = [
      msg({
        id: "other",
        role: "assistant",
        hitlData: {
          action_requests: pending.action_requests,
          status: "pending",
        },
      }),
    ];
    expect(injectPendingHitlMessage(existing, pending)).toEqual(existing);
  });
});
