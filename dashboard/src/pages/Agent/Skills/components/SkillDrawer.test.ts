import { beforeAll, describe, expect, it } from "vitest";
import {
  buildSkillMarkdown,
  isValidSkillName,
  OCTOP_EMOJI_META_KEY,
  parseSkillEmojiAndMetadata,
} from "./SkillDrawer";

// ★★ 判据【自足】（批次十四 `T-B-LAZY` · 评审 `L-2`）：
//   本文件**自己显式**去掉 `T-B-SETUP` 的 polyfill ⇒ **不依赖两张卡的先后**
//   （★「顺序是调度约束 ✗ · 判据自足是语义约束 ✓」——两卡 `blocked_by` 都是 `[]`，谁先落不确定）。
//   ★ 本文件仍然绿 ⇒ **直接证明**「三路预览改懒加载后，pdfjs 那条边**不在模块加载期**」✓。
//   ★ 反向：把 `FileViewer` 的 `lazy` 改回静态 `import` ⇒ 本文件必红（钉回见回报）。
beforeAll(() => {
  delete (globalThis as { DOMMatrix?: unknown }).DOMMatrix;
  delete (Promise as unknown as { withResolvers?: unknown }).withResolvers;
});

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

  it("writes localized presentation fields into octop metadata", () => {
    const md = buildSkillMarkdown({
      name: "demo",
      description: "Agent trigger description",
      labelZh: "演示技能",
      labelEn: "Demo Skill",
      summaryZh: "完成演示任务",
      summaryEn: "Complete demo tasks",
      emoji: "⚙️",
      metadata: [],
      body: "Do things.",
    });

    expect(md).toContain("label:");
    expect(md).toContain("zh: 演示技能");
    expect(md).toContain("en: Demo Skill");
    expect(md).toContain("summary:");
    expect(md).toContain("zh: 完成演示任务");
    expect(md).toContain("en: Complete demo tasks");
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
