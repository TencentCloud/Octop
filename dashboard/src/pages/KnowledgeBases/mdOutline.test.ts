import { describe, expect, it } from "vitest";
import { extractMarkdownOutline } from "./mdOutline";

describe("extractMarkdownOutline", () => {
  it("collects ATX headings with levels", () => {
    const items = extractMarkdownOutline(
      "# Title\n\n## A\n\ntext\n\n### B\n## C\n",
    );
    expect(items.map((i) => [i.level, i.title])).toEqual([
      [1, "Title"],
      [2, "A"],
      [3, "B"],
      [2, "C"],
    ]);
  });

  it("skips headings inside fenced code blocks", () => {
    const items = extractMarkdownOutline(
      "# Real\n\n```python\n# comment heading\n```\n\n## After\n",
    );
    expect(items.map((i) => i.title)).toEqual(["Real", "After"]);
  });

  it("records per-title occurrences so duplicate headings resolve uniquely", () => {
    const items = extractMarkdownOutline("# A\n## A\n### A\n");
    expect(items.map((i) => i.occurrence)).toEqual([0, 1, 2]);
  });

  it("trims trailing closing hashes and ignores empty headings", () => {
    const items = extractMarkdownOutline("## Closed ##\n#\n## ##\n");
    expect(items.map((i) => i.title)).toEqual(["Closed"]);
  });
});
