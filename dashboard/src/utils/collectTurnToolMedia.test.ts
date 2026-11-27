import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../pages/Chat/hooks/useChat";
import type { AssistantTurnSplit } from "../pages/Chat/utils/messageContent";
import { collectTurnToolMedia } from "./collectTurnToolMedia";

function makeToolMessage(partial: {
  id: string;
  name: string;
  arguments?: string;
  output?: string;
  attachments?: ChatMessage["attachments"];
}): ChatMessage {
  return {
    id: partial.id,
    role: "assistant",
    content: "",
    timestamp: 1,
    toolData: {
      name: partial.name,
      arguments: partial.arguments,
      output: partial.output,
    },
    attachments: partial.attachments,
  };
}

function makeSplit(tools: ChatMessage[]): AssistantTurnSplit {
  return {
    tools,
    thinkings: [],
    processSteps: tools.map((message) => ({ kind: "tool", message })),
    answerMessage: null,
  };
}

describe("collectTurnToolMedia", () => {
  it("does not surface old image paths from directory listing or file read tools", () => {
    const split = makeSplit([
      makeToolMessage({
        id: "t-ls",
        name: "ls",
        arguments: JSON.stringify({ path: "inbound" }),
        output: [
          "/Users/alice/.octop/agents/A1/inbound/1795000000_old_runner.png",
          "/Users/alice/.octop/agents/A1/inbound/1795770023_invoice.pdf",
        ].join("\n"),
      }),
      makeToolMessage({
        id: "t-exec",
        name: "execute",
        arguments: JSON.stringify({ command: "ls -la inbound/" }),
        output:
          "file: /Users/alice/.octop/agents/A1/outbound/1794000000_old_chart.png",
      }),
      makeToolMessage({
        id: "t-read",
        name: "read_file",
        arguments: JSON.stringify({
          file_path:
            "/Users/alice/.octop/agents/A1/inbound/1795000000_old_runner.png",
        }),
        output: "Binary image inspected.",
      }),
      makeToolMessage({
        id: "t-browser",
        name: "browser_use",
        arguments: JSON.stringify({ action: "screenshot" }),
        output: JSON.stringify({
          type: "image",
          source: {
            type: "url",
            url: "file:///Users/alice/.octop/agents/A1/outbound/browser.png",
            media_type: "image/png",
          },
          filename: "browser.png",
        }),
      }),
    ]);

    const media = collectTurnToolMedia(split, "A1");
    expect(media.images).toEqual([]);
    expect(media.videos).toEqual([]);
    expect(media.files).toEqual([]);
  });

  it("still surfaces media from delivery tools and octop_delivery markers", () => {
    const split = makeSplit([
      makeToolMessage({
        id: "t-send",
        name: "send_file_to_user",
        arguments: JSON.stringify({
          file_path: "outbound/invoice-summary.png",
        }),
        output: "Sent file",
      }),
      makeToolMessage({
        id: "t-shot",
        name: "desktop_screenshot",
        output:
          "Screenshot saved to /Users/alice/.octop/agents/A1/outbound/screen.png",
      }),
      makeToolMessage({
        id: "t-acp",
        name: "mcp/custom_acp_title",
        output: JSON.stringify({
          type: "image",
          octop_delivery: "send_file_to_user",
          source: {
            type: "url",
            url: "file:///Users/alice/.octop/agents/A1/outbound/acp.png",
            media_type: "image/png",
          },
          filename: "acp.png",
        }),
      }),
    ]);

    const media = collectTurnToolMedia(split, "A1");
    expect(media.images.map((item) => item.filename)).toEqual([
      "invoice-summary.png",
      "screen.png",
      "acp.png",
    ]);
  });
});
