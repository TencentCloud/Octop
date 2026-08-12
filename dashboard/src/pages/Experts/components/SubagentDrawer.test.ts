import { describe, expect, it } from "vitest";
import { buildSubagentMarkdown, parseSubagentForm } from "./SubagentDrawer";
import {
  expertPaletteColor,
  resolveExpertPalette,
} from "../../../utils/expertColor";
import { DEFAULT_PALETTE } from "../../../styles/themePalettes";

describe("SubagentDrawer color frontmatter", () => {
  it("round-trips palette hex through markdown build/parse", () => {
    const color = expertPaletteColor("tech");
    const md = buildSubagentMarkdown({
      slug: "helper",
      name: "Helper",
      description: "Helps",
      emoji: "🧰",
      color,
      body: "Do the thing.",
    });
    expect(md).toMatch(/color:\s*"?#4B74FA"?/);
    expect(parseSubagentForm(md, "helper").color).toBe(color);
  });

  it("maps empty form color to default palette for the picker", () => {
    expect(resolveExpertPalette("")).toBe(DEFAULT_PALETTE);
    expect(resolveExpertPalette(undefined)).toBe(DEFAULT_PALETTE);
  });

  it("maps picker palette back to swatch hex for the form field", () => {
    expect(expertPaletteColor(resolveExpertPalette("#4B74FA"))).toBe(
      expertPaletteColor("tech"),
    );
  });
});
