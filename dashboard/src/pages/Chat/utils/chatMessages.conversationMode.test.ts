import { describe, expect, it } from "vitest";
import { buildComposerContext } from "./chatMessages";

describe("buildComposerContext conversationMode", () => {
  it("includes conversationMode in composer context (M15 payload seed)", () => {
    const ctx = buildComposerContext({
      conversationMode: "ask",
    });
    expect(ctx).toEqual({ conversationMode: "ask" });
  });

  it("omits conversationMode when unset", () => {
    const ctx = buildComposerContext({ skills: ["a"] });
    expect(ctx?.conversationMode).toBeUndefined();
  });
});
