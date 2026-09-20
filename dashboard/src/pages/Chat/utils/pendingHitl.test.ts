import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import { findPendingAsk, hasPendingHitl } from "./pendingHitl";

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

describe("pendingHitl", () => {
  it("detects any pending HITL status", () => {
    expect(
      hasPendingHitl([
        msg({
          id: "1",
          role: "assistant",
          hitlData: {
            action_requests: [{ name: "write_file", args: {} }],
            status: "pending",
          },
        }),
      ]),
    ).toBe(true);
    expect(
      hasPendingHitl([
        msg({
          id: "1",
          role: "assistant",
          hitlData: {
            action_requests: [{ name: "write_file", args: {} }],
            status: "approved",
          },
        }),
      ]),
    ).toBe(false);
  });

  it("finds the latest pending ask with questions", () => {
    const ask = findPendingAsk([
      msg({
        id: "old",
        role: "assistant",
        hitlData: {
          action_requests: [
            {
              name: "ask_user_question",
              args: { questions: [{ question: "Old?" }] },
            },
          ],
          status: "approved",
        },
      }),
      msg({
        id: "ask",
        role: "assistant",
        hitlData: {
          action_requests: [
            {
              name: "ask_user_question",
              args: {
                questions: [
                  {
                    question: "Which DB?",
                    header: "Storage",
                    options: [{ label: "PG" }],
                  },
                ],
              },
            },
          ],
          status: "pending",
        },
      }),
    ]);
    expect(ask?.messageId).toBe("ask");
    expect(ask?.questions[0]?.question).toBe("Which DB?");
  });

  it("ignores ask pauses without parseable questions", () => {
    expect(
      findPendingAsk([
        msg({
          id: "ask",
          role: "assistant",
          hitlData: {
            action_requests: [{ name: "ask_user_question", args: {} }],
            status: "pending",
          },
        }),
      ]),
    ).toBeNull();
  });
});
