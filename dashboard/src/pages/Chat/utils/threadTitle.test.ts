import { describe, expect, it } from "vitest";
import {
  clipThreadTitle,
  formatThreadTitle,
  THREAD_TITLE_MAX,
} from "./threadTitle";

describe("clipThreadTitle", () => {
  it("returns empty for blank", () => {
    expect(clipThreadTitle(null)).toBe("");
    expect(clipThreadTitle("  ")).toBe("");
  });

  it("keeps short titles and collapses whitespace", () => {
    expect(clipThreadTitle("你好")).toBe("你好");
    expect(clipThreadTitle("a  \n  b")).toBe("a b");
  });

  it("clips with ellipsis when over max", () => {
    const long = "x".repeat(THREAD_TITLE_MAX + 5);
    const out = clipThreadTitle(long);
    expect(out.endsWith("…")).toBe(true);
    expect(out.length).toBe(THREAD_TITLE_MAX);
  });

  it("keeps exact-max titles without forcing ellipsis", () => {
    const exact = "a".repeat(THREAD_TITLE_MAX);
    expect(exact.length).toBe(THREAD_TITLE_MAX);
    expect(clipThreadTitle(exact)).toBe(exact);
    expect(clipThreadTitle(exact).endsWith("…")).toBe(false);
  });
});

describe("formatThreadTitle", () => {
  it("returns empty for blank", () => {
    expect(formatThreadTitle(null)).toBe("");
    expect(formatThreadTitle("  ")).toBe("");
  });

  it("keeps short titles", () => {
    expect(formatThreadTitle("你好")).toBe("你好");
  });

  it("does not append ellipsis to exact-max titles", () => {
    // Legitimate full-length titles (and legacy hard-cuts repaired by migration).
    const exact =
      "搜索当前热点新闻（微博热搜、知乎热榜、36氪等），整理成简洁的摘要推送给用户。格";
    expect(exact.length).toBe(THREAD_TITLE_MAX);
    expect(formatThreadTitle(exact)).toBe(exact);
  });

  it("preserves titles that already end with ellipsis within max", () => {
    const body = "a".repeat(THREAD_TITLE_MAX - 1);
    const t = `${body}…`;
    expect(t.length).toBe(THREAD_TITLE_MAX);
    expect(formatThreadTitle(t)).toBe(t);
  });
});
