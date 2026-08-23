import { describe, expect, it } from "vitest";

import {
  DEFAULT_CUSTOM_COLOR,
  brandPrimary,
  brandTokensFor,
  contrastRatio,
  customBrandTokens,
  customPaletteCssVars,
  deriveCustomBrandColors,
  mixHex,
  normalizeHexColor,
} from "./themePalettes";

describe("normalizeHexColor", () => {
  it("normalizes 3/6-digit hex with or without #", () => {
    expect(normalizeHexColor("#4B74FA")).toBe("#4b74fa");
    expect(normalizeHexColor("4b74fa")).toBe("#4b74fa");
    expect(normalizeHexColor("#ABC")).toBe("#aabbcc");
    expect(normalizeHexColor(" abc ")).toBe("#aabbcc");
  });

  it("rejects invalid input with null", () => {
    expect(normalizeHexColor("")).toBeNull();
    expect(normalizeHexColor(null)).toBeNull();
    expect(normalizeHexColor("#12345")).toBeNull();
    expect(normalizeHexColor("#1234567")).toBeNull();
    expect(normalizeHexColor("red")).toBeNull();
    expect(normalizeHexColor("rgb(1,2,3)")).toBeNull();
  });
});

describe("mixHex", () => {
  it("interpolates between colors", () => {
    expect(mixHex("#000000", "#ffffff", 0.5)).toBe("#808080");
    expect(mixHex("#000000", "#ffffff", 0)).toBe("#000000");
    expect(mixHex("#000000", "#ffffff", 1)).toBe("#ffffff");
  });
});

describe("deriveCustomBrandColors", () => {
  it("darkens light colors until white text is readable", () => {
    const { solid } = deriveCustomBrandColors("#FFFF00"); // pure yellow
    expect(contrastRatio(solid, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps already-dark colors mostly unchanged", () => {
    const { solid } = deriveCustomBrandColors("#1E3A8A");
    expect(contrastRatio(solid, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    // Stays in the same hue family (blue channel dominant).
    const r = Number.parseInt(solid.slice(1, 3), 16);
    const b = Number.parseInt(solid.slice(5, 7), 16);
    expect(b).toBeGreaterThan(r);
  });

  it("brightens dark colors for dark-mode text", () => {
    const { onDark } = deriveCustomBrandColors("#000000");
    expect(contrastRatio(onDark, "#0f1117")).toBeGreaterThanOrEqual(3);
  });
});

describe("customBrandTokens", () => {
  it("produces WCAG-AA solid states for light mode", () => {
    const tokens = customBrandTokens("#F87171").light;
    for (const c of [
      tokens.colorPrimary,
      tokens.colorPrimaryHover,
      tokens.colorPrimaryActive,
    ]) {
      expect(contrastRatio(c, "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("produces readable link colors for dark mode", () => {
    const tokens = customBrandTokens("#7C2D12").dark;
    expect(contrastRatio(tokens.colorLink, "#0f1117")).toBeGreaterThanOrEqual(
      3,
    );
  });
});

describe("brandTokensFor / brandPrimary with custom palette", () => {
  it("derives tokens from the custom hex", () => {
    const light = brandTokensFor("custom", false, "#FF0000");
    expect(light.colorPrimary).not.toBe("#FF0000"); // darkened for AA
    expect(contrastRatio(light.colorPrimary, "#FFFFFF")).toBeGreaterThanOrEqual(
      4.5,
    );
  });

  it("falls back to the default custom color when none stored", () => {
    expect(brandTokensFor("custom", true).colorLink).toBe(
      customBrandTokens(DEFAULT_CUSTOM_COLOR).dark.colorLink,
    );
  });

  it("brandPrimary passes customColor through", () => {
    expect(brandPrimary("custom", false, "#00FF00")).toBe(
      brandTokensFor("custom", false, "#00FF00").colorPrimary,
    );
  });

  it("curated palettes ignore customColor", () => {
    expect(brandPrimary("rose", false, "#00FF00")).toBe(
      brandPrimary("rose", false),
    );
  });
});

describe("customPaletteCssVars", () => {
  it("emits both light and dark blocks with the derived brand", () => {
    const light = customPaletteCssVars("#4b74fa", false);
    const dark = customPaletteCssVars("#4b74fa", true);
    expect(light).toContain(
      'html[data-palette="custom"]:not([data-theme="dark"])',
    );
    expect(dark).toContain('html[data-palette="custom"][data-theme="dark"]');
    expect(light).toContain("--fn-color-brand:");
    expect(dark).toContain("--fn-sidebar-item-active-text:");
  });
});
