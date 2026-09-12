import { describe, expect, it } from "vitest";
import { buildMentionItems } from "./MentionPickerMenu";

describe("buildMentionItems", () => {
  it("includes installed subagents as @slug picks", () => {
    const items = buildMentionItems(
      "",
      [],
      [],
      [
        {
          slug: "researcher",
          name: "研究员",
          path: "agents/researcher.md",
          emoji: "🔎",
        },
      ],
    );
    expect(items).toEqual([
      { kind: "subagent", slug: "researcher", label: "研究员" },
    ]);
  });
});
