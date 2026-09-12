import { describe, expect, it } from "vitest";
import {
  DEFAULT_CONVERSATION_MODE,
  parseConversationMode,
} from "./conversationMode";

describe("parseConversationMode", () => {
  it("accepts ask / plan / craft", () => {
    expect(parseConversationMode("ask")).toBe("ask");
    expect(parseConversationMode("plan")).toBe("plan");
    expect(parseConversationMode("craft")).toBe("craft");
  });

  it("defaults unknown / null to craft", () => {
    expect(parseConversationMode(null)).toBe(DEFAULT_CONVERSATION_MODE);
    expect(parseConversationMode(undefined)).toBe("craft");
    expect(parseConversationMode("agent")).toBe("craft");
  });
});
