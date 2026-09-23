import { splitAssistantTurn } from "../utils/messageContent";
import { afterEach, describe, expect, it } from "vitest";
import {
  appendUserMessage,
  getSnapshot,
  ingestHarnessChunk,
  removeSession,
  setHistoryPage,
} from "./chatStore";
import { parseHarnessChunk } from "../../../utils/parseHarnessChunk";

const SESSION = "model-images";
const image = () =>
  parseHarnessChunk(
    "data: " +
      JSON.stringify({
        type: "attachment",
        source: "model",
        kind: "image",
        url: "workspace://outbound/cat.png",
        filename: "cat.png",
        mime_type: "image/png",
      }),
  )!;

describe("model-generated images", () => {
  afterEach(() => removeSession(SESSION));

  function start() {
    setHistoryPage(
      SESSION,
      [
        {
          id: "old",
          role: "assistant",
          content: "Previous answer",
          status: "done",
          timestamp: 1,
          usage: { total_tokens: 10 },
        },
      ],
      { hasMore: false, nextOffset: 1 },
    );
    appendUserMessage(SESSION, {
      id: "u",
      role: "user",
      content: "cat",
      timestamp: 2,
    });
  }

  it("creates an image answer and leaves previous messages and usage intact", () => {
    start();
    ingestHarnessChunk(SESSION, image());
    ingestHarnessChunk(SESSION, { type: "usage", usage: { total_tokens: 15 } });
    ingestHarnessChunk(SESSION, { type: "done" });
    const { messages } = getSnapshot(SESSION);
    expect(messages).toHaveLength(3);
    expect(messages[0].attachments).toBeUndefined();
    expect(messages[0].usage?.total_tokens).toBe(10);
    expect(messages[2].attachments?.[0].url).toBe(
      "workspace://outbound/cat.png",
    );
    expect(messages[2].status).toBe("done");
    expect(
      splitAssistantTurn(messages.slice(2)).answerMessage?.attachments,
    ).toHaveLength(1);
    expect(messages[2].usage?.total_tokens).toBe(15);
  });

  it("combines text and images from the current model answer", () => {
    start();
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "model",
      content: "Here is the cat.",
    });
    ingestHarnessChunk(SESSION, image());
    expect(getSnapshot(SESSION).messages).toHaveLength(3);
    expect(getSnapshot(SESSION).messages[2].attachments).toHaveLength(1);
  });

  it("does not attach model images to a preceding tool result", () => {
    start();
    ingestHarnessChunk(SESSION, {
      type: "tool_call_chunk",
      id: "tool",
      name: "lookup",
      args: "{}",
    });
    ingestHarnessChunk(SESSION, {
      type: "tool_result",
      node: "tools",
      messages: [{ type: "tool", tool_call_id: "tool", content: "ok" }],
    });
    ingestHarnessChunk(SESSION, image());
    const { messages } = getSnapshot(SESSION);
    expect(messages.at(-1)?.toolData).toBeUndefined();
    expect(messages.at(-1)?.attachments).toHaveLength(1);
    expect(messages.find((m) => m.toolData)?.attachments).toBeUndefined();
  });

  it("does not overwrite earlier usage when a turn has no visible output", () => {
    start();
    ingestHarnessChunk(SESSION, { type: "usage", usage: { total_tokens: 15 } });
    ingestHarnessChunk(SESSION, { type: "done" });
    expect(getSnapshot(SESSION).messages[0].usage?.total_tokens).toBe(10);
  });
});
