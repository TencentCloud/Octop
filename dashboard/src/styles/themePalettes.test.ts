import { describe, expect, it } from "vitest";
import {
  ANTD_BRAND_TOKENS,
  VALID_PALETTES,
  brandPrimary,
} from "./themePalettes";

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map((offset) => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });

  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground: string, background: string): number {
  const foregroundLuminance = relativeLuminance(foreground);
  const backgroundLuminance = relativeLuminance(background);
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("theme palettes", () => {
  it("exposes the curated palette set", () => {
    expect(VALID_PALETTES).toEqual([
      "rose",
      "tech",
      "indigo",
      "teal",
      "violet",
      "emerald",
      "amber",
      "slate",
    ]);
  });

  it("keeps the historic Elegant Rose default brand tokens", () => {
    expect(ANTD_BRAND_TOKENS.rose.light.colorPrimary).toBe("#E85D75");
    expect(ANTD_BRAND_TOKENS.rose.light.colorPrimaryHover).toBe("#D14A62");
    expect(ANTD_BRAND_TOKENS.rose.light.colorPrimaryActive).toBe("#B83A50");
    expect(ANTD_BRAND_TOKENS.rose.dark.colorPrimary).toBe("#F08B9A");
    expect(ANTD_BRAND_TOKENS.rose.dark.colorLink).toBe("#F08B9A");
  });

  it.each(VALID_PALETTES.filter((palette) => palette !== "rose"))(
    "keeps %s solid Ant Design states readable with white text",
    (palette) => {
      for (const mode of ["light", "dark"] as const) {
        const tokens = ANTD_BRAND_TOKENS[palette][mode];
        for (const color of [
          tokens.colorPrimary,
          tokens.colorPrimaryHover,
          tokens.colorPrimaryActive,
        ]) {
          expect(contrastRatio(color, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
        }
      }
    },
  );

  it.each(VALID_PALETTES)(
    "uses the brighter %s link color for dark charts",
    (palette) => {
      expect(brandPrimary(palette, true)).toBe(
        ANTD_BRAND_TOKENS[palette].dark.colorLink,
      );
    },
  );
});
