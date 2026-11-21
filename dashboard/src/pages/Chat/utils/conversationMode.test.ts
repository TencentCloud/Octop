import { describe, expect, it } from "vitest";
import {
  isRestrictedConversationMode,
  parseConversationMode,
} from "./conversationMode";

describe("conversationMode", () => {
  it("falls back to craft", () => {
    expect(parseConversationMode(undefined)).toBe("craft");
    expect(parseConversationMode("nope")).toBe("craft");
    expect(parseConversationMode("plan")).toBe("plan");
  });

  it("treats ask and plan as restricted", () => {
    expect(isRestrictedConversationMode("ask")).toBe(true);
    expect(isRestrictedConversationMode("plan")).toBe(true);
    expect(isRestrictedConversationMode("craft")).toBe(false);
  });
});
