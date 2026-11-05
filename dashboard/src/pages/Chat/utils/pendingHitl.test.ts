import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import {
  findAutoResumableApproval,
  findPendingApproval,
  findPendingAsk,
  findPendingSecretInput,
  findPendingSecureForm,
  hasPendingHitl,
  promoteAskUserToolMessage,
  promoteSecureFormToolMessage,
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

  it("finds a resumable pending secret input", () => {
    const messages = [
      msg({
        id: "secret",
        role: "assistant",
        hitlData: {
          pending_id: "sec1",
          action_requests: [
            {
              name: "request_secret_input",
              args: { slot: "STEAM_WEB_API_KEY", prompt: "Steam key" },
            },
          ],
          status: "pending",
        },
      }),
    ];
    const pending = findPendingSecretInput(messages);
    expect(pending).not.toBeNull();
    expect(pending?.pendingId).toBe("sec1");
    expect(pending?.request.slot).toBe("STEAM_WEB_API_KEY");
    // Secret pauses are excluded from the approval/auto-resume paths.
    expect(findPendingApproval(messages)).toBeNull();
    expect(
      findAutoResumableApproval({ mode: "allow_all" }, messages),
    ).toBeNull();
  });

  it("ignores secret inputs the server cannot resume", () => {
    const messages = [
      msg({
        id: "secret",
        role: "assistant",
        hitlData: {
          action_requests: [
            {
              name: "request_secret_input",
              args: { slot: "STEAM_WEB_API_KEY", prompt: "Steam key" },
            },
          ],
          status: "pending",
        },
      }),
    ];
    expect(findPendingSecretInput(messages)).toBeNull();
    expect(hasPendingHitl(messages)).toBe(false);
  });

  it("finds a resumable pending secure form", () => {
    const messages = [
      msg({
        id: "form",
        role: "assistant",
        hitlData: {
          pending_id: "sf1",
          action_requests: [
            {
              name: "request_secure_form",
              args: {
                title: "Steam login",
                prompt: "Fill your credentials",
                fields: [
                  { id: "username", type: "text" },
                  { id: "password", type: "password" },
                ],
              },
            },
          ],
          status: "pending",
        },
      }),
    ];
    const pending = findPendingSecureForm(messages);
    expect(pending).not.toBeNull();
    expect(pending?.pendingId).toBe("sf1");
    expect(pending?.request.title).toBe("Steam login");
    expect(pending?.request.fieldCount).toBe(2);
    // Secure-form pauses are excluded from the approval/auto-resume paths.
    expect(findPendingApproval(messages)).toBeNull();
    expect(
      findAutoResumableApproval({ mode: "allow_all" }, messages),
    ).toBeNull();
  });

  it("ignores secure forms the server cannot resume", () => {
    const messages = [
      msg({
        id: "form",
        role: "assistant",
        hitlData: {
          action_requests: [
            {
              name: "request_secure_form",
              args: {
                prompt: "Fill your credentials",
                fields: [{ id: "username", type: "text" }],
              },
            },
          ],
          status: "pending",
        },
      }),
    ];
    expect(findPendingSecureForm(messages)).toBeNull();
    expect(hasPendingHitl(messages)).toBe(false);
  });

  it("promotes an unanswered request_secure_form tool bubble into a pending card", () => {
    const promoted = promoteSecureFormToolMessage(
      msg({
        id: "tool",
        role: "assistant",
        toolData: {
          name: "request_secure_form",
          arguments: JSON.stringify({
            title: "Steam login",
            prompt: "Fill your credentials",
            fields: [
              { id: "username", type: "text" },
              { id: "password", type: "password" },
            ],
          }),
        },
      }),
    );
    expect(promoted.hitlData?.status).toBe("pending");
    expect(promoted.hitlData?.pending_id).toBeUndefined();
    expect(promoted.hitlData?.action_requests[0]?.name).toBe(
      "request_secure_form",
    );
    // Not resumable → never docked, never blocks the composer.
    expect(findPendingSecureForm([promoted])).toBeNull();
    expect(hasPendingHitl([promoted])).toBe(false);
  });

  it("does not promote answered or foreign tool bubbles", () => {
    const answered = promoteSecureFormToolMessage(
      msg({
        id: "tool",
        role: "assistant",
        toolData: {
          name: "request_secure_form",
          arguments: "{}",
          output: '{"ok": true}',
        },
      }),
    );
    expect(answered.hitlData).toBeUndefined();
    const foreign = promoteSecureFormToolMessage(
      msg({
        id: "tool",
        role: "assistant",
        toolData: { name: "web_fetch", arguments: "{}" },
      }),
    );
    expect(foreign.hitlData).toBeUndefined();
  });
});
