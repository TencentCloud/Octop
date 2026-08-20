import { describe, expect, it } from "vitest";
import {
  formatRunUsage,
  resolveTurnModelOverride,
  resolveTurnModelRef,
  assistantTurnsFromEnd,
  userTurnsFromEnd,
} from "./chatMessages";

describe("formatRunUsage", () => {
  it("shows cached input and the cache hit rate", () => {
    expect(
      formatRunUsage(
        {
          input_tokens: 1_000,
          cache_read_tokens: 700,
          output_tokens: 80,
          total_tokens: 1_080,
        },
        {
          input: "input",
          cacheHit: "cache hit",
          output: "output",
          total: "total",
        },
      ),
    ).toBe("1000 input / 700 cache hit (70%) / 80 output / 1080 total");
  });
});

describe("resolveTurnModelRef", () => {
  it("sends only an explicit composer selection", () => {
    expect(resolveTurnModelRef("p/picked", null)).toBe("p/picked");
  });

  it("omits model when composer is Auto so backend can resolve expert default", () => {
    expect(resolveTurnModelRef(null, null)).toBeNull();
    expect(resolveTurnModelRef("", null)).toBeNull();
  });
});

describe("userTurnsFromEnd", () => {
  it("counts user turns from the selected message through the latest", () => {
    const messages = [
      { id: "u1", role: "user" },
      { id: "a1", role: "assistant" },
      { id: "u2", role: "user" },
      { id: "a2", role: "assistant" },
      { id: "u3", role: "user" },
    ];
    expect(userTurnsFromEnd(messages, "u2")).toBe(2);
    expect(userTurnsFromEnd(messages, "u3")).toBe(1);
    expect(userTurnsFromEnd(messages, "u1")).toBe(3);
    expect(userTurnsFromEnd(messages, "missing")).toBe(0);
  });
});

describe("assistantTurnsFromEnd", () => {
  it("counts answer turns and skips tool messages", () => {
    const messages = [
      { id: "u1", role: "user" },
      { id: "t1", role: "assistant", toolData: { name: "search_knowledge" } },
      { id: "a1", role: "assistant" },
      { id: "u2", role: "user" },
      { id: "a2", role: "assistant" },
    ];
    expect(assistantTurnsFromEnd(messages, "a1")).toBe(2);
    expect(assistantTurnsFromEnd(messages, "a2")).toBe(1);
    expect(assistantTurnsFromEnd(messages, "missing")).toBe(0);
  });
});
