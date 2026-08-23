import { describe, expect, it } from "vitest";
import { parseOctopToolOutput } from "./parseToolOutput";
import { isPinnedToolUiMessage, partitionPinnedTools } from "./isPinnedToolUi";
import type { ChatMessage } from "../../pages/Chat/hooks/useChat";
import {
  countProcessStats,
  type AssistantTurnSplit,
} from "../../pages/Chat/utils/messageContent";

describe("parseOctopToolOutput object input", () => {
  it("accepts already-parsed envelope objects", () => {
    const parsed = parseOctopToolOutput({
      octop_ui: { renderer: "demo_card", version: 1 },
      data: { title: "Hello", count: 1 },
      text: "Hello",
    });
    expect(parsed.octopUi?.renderer).toBe("demo_card");
    expect(parsed.data).toEqual({ title: "Hello", count: 1 });
  });
});

describe("isPinnedToolUiMessage", () => {
  it("pins messages whose output has octop_ui", () => {
    const msg = {
      id: "1",
      role: "assistant",
      content: "",
      timestamp: 0,
      toolData: {
        name: "demo_ui_card",
        output: JSON.stringify({
          octop_ui: { renderer: "demo_card" },
          data: { title: "T", count: 1 },
        }),
      },
    } as ChatMessage;
    expect(isPinnedToolUiMessage(msg)).toBe(true);
  });

  it("does not pin plain tool output", () => {
    const msg = {
      id: "2",
      role: "assistant",
      content: "",
      timestamp: 0,
      toolData: { name: "echo", output: "hello" },
    } as ChatMessage;
    expect(isPinnedToolUiMessage(msg)).toBe(false);
  });
});

describe("partitionPinnedTools + process summary counts", () => {
  it("keeps pinned tools in full-split counts after they leave the fold", () => {
    const toolMsg = {
      id: "tool-1",
      role: "assistant",
      content: "",
      timestamp: 0,
      toolData: {
        name: "get_server_status",
        output: JSON.stringify({
          octop_ui: { renderer: "server_status_card" },
          data: { ok: true },
        }),
      },
    } as ChatMessage;

    const split: AssistantTurnSplit = {
      tools: [toolMsg],
      thinkings: [
        { messageId: "t1", content: "think A" },
        { messageId: "t2", content: "think B" },
      ],
      processSteps: [
        {
          kind: "thinking",
          item: { messageId: "t1", content: "think A" },
        },
        { kind: "tool", message: toolMsg },
        {
          kind: "thinking",
          item: { messageId: "t2", content: "think B" },
        },
      ],
      answerMessage: null,
    };

    const { pinned, folded } = partitionPinnedTools(split);
    expect(pinned).toHaveLength(1);
    expect(folded.tools).toHaveLength(0);
    // Fold alone would wrongly drop the tool from the headline.
    expect(countProcessStats(folded)).toEqual({
      toolCount: 0,
      thinkingCount: 2,
    });
    // Headline must use the full turn so the tool still counts.
    expect(countProcessStats(split)).toEqual({
      toolCount: 1,
      thinkingCount: 2,
    });
  });
});
