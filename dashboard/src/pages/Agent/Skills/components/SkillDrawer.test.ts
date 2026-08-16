import { describe, expect, it } from "vitest";
import {
  buildSkillMarkdown,
  OCTOP_EMOJI_META_KEY,
  parseSkillEmojiAndMetadata,
} from "./SkillDrawer";

describe("SkillDrawer emoji metadata", () => {
  it("writes octop.emoji into frontmatter from the emoji field", () => {
    const md = buildSkillMarkdown({
      name: "demo",
      description: "A demo skill",
      emoji: "⚙️",
      metadata: [],
      body: "Do things.",
    });
    expect(md).toMatch(/emoji:\s*"?⚙️"?/);
    expect(md).toContain("octop:");
  });

  it("extracts emoji from flattened metadata and keeps other keys", () => {
    const { emoji, metadata } = parseSkillEmojiAndMetadata([
      { key: OCTOP_EMOJI_META_KEY, value: "🔧" },
      { key: "octop.requires.bins", value: "git" },
    ]);
    expect(emoji).toBe("🔧");
    expect(metadata).toEqual([{ key: "octop.requires.bins", value: "git" }]);
  });
});
