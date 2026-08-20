import { describe, expect, it } from "vitest";
import type { ChatMessage } from "./sseHelpers";
import { collectChatFilePaths } from "./useChatFileDetection";

function toolMsg(partial: {
  name: string;
  arguments: string;
  output?: string;
  content?: string;
}): ChatMessage {
  return {
    id: "t1",
    role: "assistant",
    content: partial.content ?? "",
    timestamp: 1,
    toolData: {
      name: partial.name,
      arguments: partial.arguments,
      output: partial.output,
    },
  };
}

describe("collectChatFilePaths", () => {
  it("prefers a structured args path over result text", () => {
    const paths = collectChatFilePaths([
      toolMsg({
        name: "write_file",
        arguments: JSON.stringify({ path: "generated/report.pptx" }),
        output: "Wrote outbound/screenshots/harness.png",
        content: "Also mentioned outbound/screenshots/harness.png",
      }),
    ]);
    expect(paths).toEqual(["generated/report.pptx"]);
  });

  it("scans tool output when args have no path", () => {
    const paths = collectChatFilePaths([
      toolMsg({
        name: "write_file",
        arguments: JSON.stringify({ content: "hello" }),
        output: "Wrote /home/wally/.octop/agents/A1/outbound/notes.md",
      }),
    ]);
    expect(paths).toEqual(["/home/wally/.octop/agents/A1/outbound/notes.md"]);
  });
});
