import { describe, expect, it } from "vitest";
import { SUBAGENT_EMOJI_OPTIONS } from "./subagentEmojis";

describe("SUBAGENT_EMOJI_OPTIONS", () => {
  it("starts with the default robot emoji", () => {
    expect(SUBAGENT_EMOJI_OPTIONS[0]).toBe("🤖");
  });

  it("has no duplicate entries", () => {
    expect(new Set(SUBAGENT_EMOJI_OPTIONS).size).toBe(
      SUBAGENT_EMOJI_OPTIONS.length,
    );
  });

  it("covers a full catalog-sized set for picker browsing", () => {
    expect(SUBAGENT_EMOJI_OPTIONS.length).toBeGreaterThanOrEqual(100);
  });
});
