import { describe, expect, it } from "vitest";
import {
  buildSkillMarkdown,
  isValidSkillName,
  OCTOP_EMOJI_META_KEY,
  parseSkillEmojiAndMetadata,
} from "./SkillDrawer";

describe("isValidSkillName", () => {
  it("accepts CJK, letters, digits and . _ -", () => {
    expect(isValidSkillName("天气查询")).toBe(true);
    expect(isValidSkillName("weather-analysis")).toBe(true);
    expect(isValidSkillName("weather_query.v2")).toBe(true);
  });

  it("rejects filesystem-hostile characters and leading dot", () => {
    expect(isValidSkillName(".hidden")).toBe(false);
    expect(isValidSkillName("a/b")).toBe(false);
    expect(isValidSkillName("a\\b")).toBe(false);
    expect(isValidSkillName('a:b*c?d"e<f>g|h')).toBe(false);
    expect(isValidSkillName("line\nbreak")).toBe(false);
    expect(isValidSkillName("")).toBe(false);
    expect(isValidSkillName("x".repeat(65))).toBe(false);
  });
});

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
