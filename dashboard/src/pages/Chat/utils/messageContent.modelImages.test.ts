import { describe, expect, it } from "vitest";
import { convertHistoryMessages } from "../hooks/useChat";
import { splitAssistantTurn, toAnswerOnlyMessage } from "./messageContent";

describe("model image answers", () => {
  it.each(["", "Here is the cat."])(
    "keeps generated images visible after history reload (text: %j)",
    (text) => {
      const messages = convertHistoryMessages(
        [
          {
            role: "assistant",
            content: [
              {
                type: "image_url",
                image_url: { url: "workspace://outbound/generated/cat.png" },
                workspace_path: "outbound/generated/cat.png",
                filename: "cat.png",
                mime_type: "image/png",
              },
              ...(text ? [{ type: "text", text }] : []),
            ],
          },
        ],
        "main",
      );
      const { answerMessage } = splitAssistantTurn(messages);
      expect(answerMessage).not.toBeNull();
      const answer = toAnswerOnlyMessage(answerMessage!);
      expect(answer.content).toBe(text);
      expect(answer.attachments).toHaveLength(1);
      expect(answer.attachments?.[0].workspacePath).toBe(
        "outbound/generated/cat.png",
      );
      expect(answer.attachments?.[0].url).toContain("/api/agents/main/");
    },
  );

  it("keeps a stream failure separate from the image answer", () => {
    const image = {
      id: "image",
      role: "assistant" as const,
      content: "",
      timestamp: 1,
      attachments: [
        { url: "workspace://outbound/cat.png", kind: "image" as const },
      ],
    };
    const { answerMessage, errorMessages } = splitAssistantTurn([
      image,
      {
        id: "error",
        role: "assistant",
        content: "The model returned no text, images or tool calls.",
        status: "error",
        timestamp: 2,
      },
    ]);
    expect(answerMessage?.attachments).toEqual(image.attachments);
    expect(answerMessage?.content).toBe("");
    expect(errorMessages).toHaveLength(1);
    expect(errorMessages?.[0].content).toContain("no text");
  });

  it("keeps tool media in the tool section", () => {
    const { answerMessage, tools } = splitAssistantTurn([
      {
        id: "tool",
        role: "assistant",
        content: "",
        timestamp: 1,
        toolData: { name: "lookup", output: "ok" },
        attachments: [{ url: "https://example.com/cat.png", kind: "image" }],
      },
    ]);
    expect(answerMessage).toBeNull();
    expect(tools).toHaveLength(1);
  });
});
