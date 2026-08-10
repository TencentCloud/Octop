import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/useChat";
import { layoutAssistantTurnHitl } from "./layoutAssistantTurnHitl";

function msg(
  partial: Partial<ChatMessage> & Pick<ChatMessage, "id" | "role">,
): ChatMessage {
  return {
    content: "",
    timestamp: 0,
    ...partial,
  };
}

describe("layoutAssistantTurnHitl", () => {
  it("returns all messages as trailing when no HITL is present", () => {
    const messages = [
      msg({
        id: "a1",
        role: "assistant",
        content: "hi",
        toolData: { name: "bash" },
      }),
      msg({ id: "a2", role: "assistant", content: "done" }),
    ];
    expect(layoutAssistantTurnHitl(messages)).toEqual({
      segments: [],
      trailingMessages: messages,
    });
  });

  it("keeps a single pending HITL as one segment", () => {
    const tool = msg({
      id: "t1",
      role: "assistant",
      toolData: { name: "execute" },
    });
    const hitl = msg({
      id: "h1",
      role: "assistant",
      hitlData: {
        action_requests: [{ name: "execute", args: { command: "ls" } }],
        status: "pending",
      },
    });
    expect(layoutAssistantTurnHitl([tool, hitl])).toEqual({
      segments: [{ processMessages: [tool], hitlMessage: hitl }],
      trailingMessages: [],
    });
  });

  it("surfaces a follow-up pending HITL after an approved one", () => {
    const tool1 = msg({
      id: "t1",
      role: "assistant",
      toolData: { name: "execute" },
    });
    const hitl1 = msg({
      id: "h1",
      role: "assistant",
      hitlData: {
        action_requests: [{ name: "execute", args: { command: "ls /etc" } }],
        status: "approved",
      },
    });
    const tool2 = msg({
      id: "t2",
      role: "assistant",
      toolData: { name: "execute" },
    });
    const hitl2 = msg({
      id: "h2",
      role: "assistant",
      hitlData: {
        action_requests: [
          { name: "execute", args: { command: "ls /private/etc" } },
        ],
        status: "pending",
      },
    });

    const layout = layoutAssistantTurnHitl([tool1, hitl1, tool2, hitl2]);
    expect(layout.segments).toHaveLength(2);
    expect(layout.segments[0]).toEqual({
      processMessages: [tool1],
      hitlMessage: hitl1,
    });
    expect(layout.segments[1]).toEqual({
      processMessages: [tool2],
      hitlMessage: hitl2,
    });
    expect(layout.trailingMessages).toEqual([]);
    expect(layout.segments[1].hitlMessage.hitlData?.status).toBe("pending");
  });

  it("keeps answer text after the last HITL in trailingMessages", () => {
    const hitl = msg({
      id: "h1",
      role: "assistant",
      hitlData: {
        action_requests: [{ name: "bash", args: {} }],
        status: "approved",
      },
    });
    const answer = msg({
      id: "a1",
      role: "assistant",
      content: "all done",
    });
    expect(layoutAssistantTurnHitl([hitl, answer])).toEqual({
      segments: [{ processMessages: [], hitlMessage: hitl }],
      trailingMessages: [answer],
    });
  });
});
