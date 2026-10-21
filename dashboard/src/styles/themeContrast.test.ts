import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync(join(__dirname, "theme-vars.css"), "utf-8");

type Rgb = [number, number, number];

function parseHex(hex: string): Rgb {
  const c = hex.replace("#", "");
  if (c.length === 3) {
    return [
      parseInt(c[0] + c[0], 16),
      parseInt(c[1] + c[1], 16),
      parseInt(c[2] + c[2], 16),
    ];
  }
  return [
    parseInt(c.slice(0, 2), 16),
    parseInt(c.slice(2, 4), 16),
    parseInt(c.slice(4, 6), 16),
  ];
}

function blendOver(rgba: string, bg: Rgb): Rgb {
  const m = rgba.match(
    /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)/,
  );
  if (!m) throw new Error(`unparseable colour: ${rgba}`);
  const a = m[4] === undefined ? 1 : Number(m[4]);
  return [
    Math.round(Number(m[1]) * a + bg[0] * (1 - a)),
    Math.round(Number(m[2]) * a + bg[1] * (1 - a)),
    Math.round(Number(m[3]) * a + bg[2] * (1 - a)),
  ];
}

function luminance([r, g, b]: Rgb): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(fg: Rgb, bg: Rgb): number {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
}

function token(name: string, block: string): string {
  const m = block.match(new RegExp(`${name}:\\s*([^;]+);`));
  if (!m) throw new Error(`token ${name} not found`);
  return m[1].trim();
}

const lightBlock = css.slice(
  css.indexOf("LIGHT THEME"),
  css.indexOf("DARK THEME"),
);
const darkBlock = css.slice(
  css.indexOf("DARK THEME"),
  css.indexOf("Brand palettes"),
);

/**
 * A11Y-6 guard: the tokens below failed WCAG 1.4.3 (4.5:1 for text) in the
 * audited build. Pin them at ≥4.5:1 against their actual backgrounds so a
 * palette tweak cannot silently regress contrast again.
 */
describe("theme contrast floor (audit A11Y-6)", () => {
  const WHITE = parseHex("#ffffff");
  const DARK_BG = parseHex("#0f1117");

  it("light: brand text and sidebar active text ≥ 4.5:1 on white/light surfaces", () => {
    const brand = parseHex(token("--fn-color-brand", lightBlock));
    const textBrand = parseHex(token("--fn-text-brand", lightBlock));
    const sidebarText = parseHex(
      token("--fn-sidebar-item-active-text", lightBlock),
    );
    const sidebarBg = parseHex(
      token("--fn-sidebar-item-active-bg", lightBlock),
    );
    expect(contrast(WHITE, brand)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(textBrand, WHITE)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarText, WHITE)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(sidebarText, sidebarBg)).toBeGreaterThanOrEqual(4.5);
  });

  it("light: tertiary and placeholder text ≥ 4.5:1 on white", () => {
    const tertiary = parseHex(token("--fn-text-tertiary", lightBlock));
    const placeholder = parseHex(token("--fn-text-placeholder", lightBlock));
    expect(contrast(tertiary, WHITE)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(placeholder, WHITE)).toBeGreaterThanOrEqual(4.5);
  });

  it("dark: tertiary and placeholder text ≥ 4.5:1 on the dark layout bg", () => {
    const tertiary = blendOver(token("--fn-text-tertiary", darkBlock), DARK_BG);
    const placeholder = blendOver(
      token("--fn-text-placeholder", darkBlock),
      DARK_BG,
    );
    expect(contrast(tertiary, DARK_BG)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(placeholder, DARK_BG)).toBeGreaterThanOrEqual(4.5);
  });

  it("dark: on-brand text ≥ 4.5:1 on the dark brand fill", () => {
    const onBrand = parseHex(token("--fn-color-on-brand", darkBlock));
    const brand = parseHex(token("--fn-color-brand", darkBlock));
    expect(contrast(onBrand, brand)).toBeGreaterThanOrEqual(4.5);
  });

  it("light: semantic *-text tokens ≥ 4.5:1 on white", () => {
    for (const name of ["--fn-color-warning-text"]) {
      const c = parseHex(token(name, lightBlock));
      expect(contrast(c, WHITE)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
