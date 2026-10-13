import { describe, expect, it } from "vitest";
import {
  extractAskQuestions,
  normalizeHitlRequest,
  questionsFromUnknown,
} from "./hitl";

describe("hitl ask payload", () => {
  it("unwraps a LangGraph interrupt envelope", () => {
    const raw = normalizeHitlRequest({
      id: "int-1",
      value: {
        action_requests: [
          {
            name: "ask_user_question",
            args: { questions: [{ question: "Which DB?" }] },
          },
        ],
      },
    });
    expect(extractAskQuestions(raw.action_requests as never)).toEqual([
      {
        question: "Which DB?",
        header: undefined,
        multi_select: false,
        options: [],
      },
    ]);
  });

  it("parses questions from a JSON argument string", () => {
    expect(
      questionsFromUnknown(
        JSON.stringify({
          questions: [{ question: "Ship it?", options: [{ label: "Yes" }] }],
        }),
      ),
    ).toEqual([
      {
        question: "Ship it?",
        header: undefined,
        multi_select: false,
        options: [{ label: "Yes", description: undefined }],
      },
    ]);
  });
});
