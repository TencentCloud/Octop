import { afterEach, describe, expect, it } from "vitest";
import { getSnapshot, ingestHarnessChunk, removeSession } from "./chatStore";

const SESSION = "test-hitl-ask";

describe("ask_user_question HITL ingest", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("merges hitl_required onto the unanswered ask tool and stamps pending_id", () => {
    ingestHarnessChunk(SESSION, {
      type: "tool_call_chunk",
      name: "ask_user_question",
      id: "call-1",
      args: JSON.stringify({
        questions: [{ question: "Which DB?" }],
      }),
    });
    ingestHarnessChunk(SESSION, {
      type: "hitl_required",
      request: {
        pending_id: "ab12",
        action_requests: [
          {
            name: "ask_user_question",
            args: { questions: [{ question: "Which DB?" }] },
          },
        ],
      },
    });

    const messages = getSnapshot(SESSION).messages;
    expect(messages).toHaveLength(1);
    expect(messages[0]?.hitlData?.pending_id).toBe("ab12");
    expect(messages[0]?.toolData?.name).toBe("ask_user_question");
    expect(messages[0]?.status).toBe("done");
  });

  it("does not overwrite a pending tool approval with an ask interrupt", () => {
    ingestHarnessChunk(SESSION, {
      type: "hitl_required",
      request: {
        pending_id: "appr",
        action_requests: [{ name: "execute", args: { command: "ls" } }],
      },
    });
    ingestHarnessChunk(SESSION, {
      type: "hitl_required",
      request: {
        pending_id: "ask1",
        action_requests: [
          {
            name: "ask_user_question",
            args: { questions: [{ question: "Go?" }] },
          },
        ],
      },
    });

    const messages = getSnapshot(SESSION).messages;
    expect(messages).toHaveLength(2);
    expect(messages[0]?.hitlData?.pending_id).toBe("appr");
    expect(messages[0]?.hitlData?.action_requests?.[0]?.name).toBe("execute");
    expect(messages[1]?.hitlData?.pending_id).toBe("ask1");
  });
});
