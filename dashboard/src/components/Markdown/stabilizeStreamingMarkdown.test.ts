import { describe, expect, it } from "vitest";
import { stabilizeStreamingMarkdown } from "./stabilizeStreamingMarkdown";

describe("stabilizeStreamingMarkdown", () => {
  it("leaves complete fences alone", () => {
    const src = "before\n```js\nconst x = 1\n```\nafter";
    expect(stabilizeStreamingMarkdown(src)).toBe(src);
  });

  it("closes an open fence so trailing prose is not swallowed", () => {
    const src = "intro\n```python\nprint(1";
    expect(stabilizeStreamingMarkdown(src)).toBe(
      "intro\n```python\nprint(1\n```",
    );
  });

  it("handles tilde fences", () => {
    const src = "~~~\ncode";
    expect(stabilizeStreamingMarkdown(src)).toBe("~~~\ncode\n~~~");
  });

  it("is a no-op for empty content", () => {
    expect(stabilizeStreamingMarkdown("")).toBe("");
  });
});
