import { describe, expect, it } from "vitest";
import {
  DEFAULT_SUBAGENT_ACCENT,
  expertPaletteColor,
  resolveExpertPalette,
  resolveSubagentAccent,
} from "./expertColor";

describe("resolveExpertPalette", () => {
  it("matches exact curated swatches", () => {
    expect(resolveExpertPalette("#E85D75")).toBe("rose");
    expect(resolveExpertPalette("#6366F1")).toBe("indigo");
  });

  it("falls back to rose when color is missing", () => {
    expect(resolveExpertPalette(null)).toBe("rose");
    expect(resolveExpertPalette(undefined)).toBe("rose");
  });

  it("snaps nearby template pastels onto the nearest swatch", () => {
    expect(resolveExpertPalette("#e8f4ff")).toBe("indigo");
  });

  it("returns the hex for a palette key", () => {
    expect(expertPaletteColor("amber")).toBe("#F59E0B");
  });
});

describe("resolveSubagentAccent", () => {
  it("returns hex as-is", () => {
    expect(resolveSubagentAccent("#4B74FA")).toBe("#4B74FA");
  });

  it("maps curated palette keys onto swatch hex", () => {
    expect(resolveSubagentAccent("tech")).toBe(expertPaletteColor("tech"));
    expect(resolveSubagentAccent("Rose")).toBe(expertPaletteColor("rose"));
  });

  it("keeps CSS named colors for catalog frontmatter", () => {
    expect(resolveSubagentAccent("orange")).toBe("orange");
    expect(resolveSubagentAccent("blue")).toBe("blue");
  });

  it("falls back when color is missing or unsafe", () => {
    expect(resolveSubagentAccent(null)).toBe(DEFAULT_SUBAGENT_ACCENT);
    expect(resolveSubagentAccent("")).toBe(DEFAULT_SUBAGENT_ACCENT);
    expect(resolveSubagentAccent("red; background: red")).toBe(
      DEFAULT_SUBAGENT_ACCENT,
    );
  });
});
