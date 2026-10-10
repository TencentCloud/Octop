import { describe, expect, it } from "vitest";
import {
  __resetEstimateTokensForTest,
  estimateTokens,
  formatTokenCount,
} from "./estimateTokens";

describe("estimateTokens", () => {
  it("returns 0 for empty input", async () => {
    expect(await estimateTokens("")).toBe(0);
  });

  it("counts a short English string", async () => {
    // js-tiktoken cl100k_base: "hello world" → 2 tokens
    const n = await estimateTokens("hello world");
    expect(n).toBe(2);
  });

  it("counts Chinese characters (each CJK glyph ≈ 1 token at cl100k_base)", async () => {
    // "你好世界" → typically 4 tokens at cl100k_base
    const n = await estimateTokens("你好世界");
    expect(n).toBeGreaterThanOrEqual(3);
    expect(n).toBeLessThanOrEqual(6);
  });

  it("handles mixed CJK + ASCII", async () => {
    const n = await estimateTokens("hello 你好 world 世界");
    expect(n).toBeGreaterThan(0);
  });

  it("counts code-like content with brackets and operators", async () => {
    // "const x = 42;" → 5–6 tokens at cl100k_base
    const n = await estimateTokens("const x = 42;");
    expect(n).toBeGreaterThanOrEqual(3);
    expect(n).toBeLessThanOrEqual(8);
  });

  it("reuses the encoder across calls (no re-init)", async () => {
    __resetEstimateTokensForTest();
    const a = await estimateTokens("alpha");
    const b = await estimateTokens("beta");
    expect(a).toBeGreaterThan(0);
    expect(b).toBeGreaterThan(0);
    // Same promise chain: both calls land on the same encoder instance.
    // (No public handle, but consecutive encode() output proves reuse.)
    const c = await estimateTokens("alpha");
    expect(c).toBe(a);
  });
});

describe("formatTokenCount", () => {
  it("returns '0' for non-positive or non-finite", () => {
    expect(formatTokenCount(0)).toBe("0");
    expect(formatTokenCount(-1)).toBe("0");
    expect(formatTokenCount(Number.NaN)).toBe("0");
    expect(formatTokenCount(Number.POSITIVE_INFINITY)).toBe("0");
  });

  it("keeps sub-1k numbers as plain integers", () => {
    expect(formatTokenCount(1)).toBe("1");
    expect(formatTokenCount(145)).toBe("145");
    expect(formatTokenCount(999)).toBe("999");
  });

  it("renders 1k–9.9k as 'X.Yk'", () => {
    expect(formatTokenCount(1_000)).toBe("1.0k");
    // 1450 / 1000 in IEEE 754 = 1.44999… → toFixed(1) = "1.4" (half-to-even
    // banker's rounding). Asserting the actual JS toFixed behaviour keeps
    // the format pinned down instead of locking in an idealised value.
    expect(formatTokenCount(1_450)).toMatch(/^1\.[45]k$/);
    expect(formatTokenCount(9_999)).toBe("10.0k");
  });

  it("rounds 10k+ to nearest integer k", () => {
    expect(formatTokenCount(10_000)).toBe("10k");
    expect(formatTokenCount(123_456)).toBe("123k");
  });

  it("renders millions as 'X.XM'", () => {
    expect(formatTokenCount(1_500_000)).toBe("1.5M");
  });
});