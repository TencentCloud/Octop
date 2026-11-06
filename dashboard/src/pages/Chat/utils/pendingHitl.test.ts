import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import {
  findAutoResumableApproval,
  findPendingApproval,
  findPendingAsk,
  findPendingSecret,
  hasPendingHitl,
  promoteAskUserToolMessage,
} from "./pendingHitl";

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
          pending_id: "ab12",
        },
      }),
    ]);
    expect(ask?.messageId).toBe("ask");
    expect(ask?.questions[0]?.question).toBe("Which DB?");
  });

  it("finds the latest pending tool approval and skips questions", () => {
    const pending = findPendingApproval([
      msg({
        id: "old",
        role: "assistant",
        hitlData: {
          action_requests: [{ name: "write_file", args: {} }],
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
              args: { questions: [{ question: "Which DB?" }] },
            },
          ],
          status: "pending",
        },
      }),
      msg({
        id: "tool",
        role: "assistant",
        hitlData: {
          action_requests: [{ name: "execute", args: { command: "ls" } }],
          status: "pending",
        },
      }),
    ]);
    expect(pending?.messageId).toBe("tool");
    expect(pending?.actions[0]?.name).toBe("execute");
  });

  it("auto-resumes tool approvals under allow-all but not questions", () => {
    const messages = [
      msg({
        id: "tool",
        role: "assistant",
        hitlData: {
          action_requests: [{ name: "execute", args: { command: "ls" } }],
          status: "pending",
        },
      }),
    ];
    expect(
      findAutoResumableApproval({ mode: "allow_all" }, messages)?.messageId,
    ).toBe("tool");
    expect(
      findAutoResumableApproval(
        { mode: "allow_tools", tools: ["execute"] },
        messages,
      )?.messageId,
    ).toBe("tool");
    expect(
      findAutoResumableApproval(
        { mode: "allow_tools", tools: ["write_file"] },
        messages,
      ),
    ).toBeNull();
    expect(findAutoResumableApproval({ mode: "ask" }, messages)).toBeNull();
    expect(
      findAutoResumableApproval({ mode: "allow_all" }, [
        msg({
          id: "ask",
          role: "assistant",
          hitlData: {
            action_requests: [
              {
                name: "ask_user_question",
                args: { questions: [{ question: "Which?" }] },
              },
            ],
            status: "pending",
            pending_id: "ab12",
          },
        }),
      ]),
    ).toBeNull();
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

  it("ignores reconstructed asks that the server cannot resume", () => {
    const reconstructed = promoteAskUserToolMessage(
      msg({
        id: "tool",
        role: "assistant",
        toolData: {
          name: "ask_user_question",
          arguments: JSON.stringify({
            questions: [{ question: "Which DB?", options: [{ label: "PG" }] }],
          }),
        },
      }),
    );
    expect(reconstructed.hitlData?.status).toBe("pending");
    expect(findPendingAsk([reconstructed])).toBeNull();
    expect(hasPendingHitl([reconstructed])).toBe(false);
  });

  it("finds a pending secret card and reads its metadata", () => {
    const message = msg({
      id: "sec",
      role: "assistant",
      hitlData: {
        action_requests: [
          {
            name: "request_secret_file",
            args: {
              path: "hr.token",
              prompt: "HR token",
              _secret_card: { path: "/ws/.octop/auth/hr.token", exists: true },
            },
          },
        ],
        status: "pending",
        pending_id: "p1",
      },
    });
    const found = findPendingSecret([message]);
    expect(found?.pendingId).toBe("p1");
    expect(found?.request.meta.path).toBe("/ws/.octop/auth/hr.token");
    expect(found?.request.meta.exists).toBe(true);
    // secret cards are not approvals and not questions
    expect(findPendingApproval([message])).toBeNull();
    expect(findPendingAsk([message])).toBeNull();
    expect(hasPendingHitl([message])).toBe(true);
    // without a pending_id the server cannot resume it — not blocking
    const orphan = msg({
      id: "sec2",
      role: "assistant",
      hitlData: {
        action_requests: [{ name: "request_secret_file", args: {} }],
        status: "pending",
      },
    });
    expect(findPendingSecret([orphan])).toBeNull();
    expect(hasPendingHitl([orphan])).toBe(false);
  });
});
