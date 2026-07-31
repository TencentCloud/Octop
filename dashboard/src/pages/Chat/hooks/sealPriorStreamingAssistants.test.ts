import { describe, expect, it } from "vitest";
import type { ChatMessage } from "./useChat";
import { sealPriorStreamingAssistants } from "./sealPriorStreamingAssistants";

function msg(
  partial: Partial<ChatMessage> & Pick<ChatMessage, "id" | "role" | "status">,
): ChatMessage {
  return {
    content: "",
    timestamp: 0,
    ...partial,
  };
}

describe("sealPriorStreamingAssistants", () => {
  it("seals streaming text bubbles so a new bubble won't leave multiple carets", () => {
    const input = [
      msg({ id: "a1", role: "assistant", content: "hi", status: "streaming" }),
      msg({
        id: "a2",
        role: "assistant",
        status: "streaming",
        toolData: { name: "shell", arguments: "" },
      }),
    ];
    const out = sealPriorStreamingAssistants(input);
    expect(out[0].status).toBe("done");
    // In-flight tools stay streaming (caller may append another text bubble).
    expect(out[1].status).toBe("streaming");
    expect(out[1]).toBe(input[1]);
  });

  it("seals the previous text tail even when it is the last message", () => {
    const input = [
      msg({ id: "a1", role: "assistant", content: "hi", status: "done" }),
      msg({ id: "a2", role: "assistant", content: "more", status: "streaming" }),
    ];
    const out = sealPriorStreamingAssistants(input);
    expect(out[1].status).toBe("done");
  });

  it("is a no-op when nothing text-like is streaming", () => {
    const input = [
      msg({ id: "a1", role: "assistant", content: "hi", status: "done" }),
      msg({
        id: "a2",
        role: "assistant",
        status: "streaming",
        toolData: { name: "shell", arguments: "" },
      }),
    ];
    expect(sealPriorStreamingAssistants(input)).toBe(input);
  });
});
