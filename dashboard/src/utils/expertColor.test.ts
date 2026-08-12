import { describe, expect, it } from "vitest";
import { expertPaletteColor, resolveExpertPalette } from "./expertColor";

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
