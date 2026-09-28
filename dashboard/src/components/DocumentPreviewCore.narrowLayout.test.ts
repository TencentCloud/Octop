import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/** Body of the first rule whose selector is exactly ``selector``. */
function ruleBody(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
  if (!match) throw new Error(`missing rule: ${selector}`);
  return match[1];
}

// A page wider than the preview must overflow to the right (scrollable), not
// to both sides: centring the flex item puts its left part out of reach
// (#1262). Auto margins keep pages centred whenever they fit.
describe("document previews on narrow screens", () => {
  it("keeps the left edge of Word pages reachable", () => {
    const css = readFileSync(
      resolve(__dirname, "DocumentPreviewCore.module.less"),
      "utf8",
    );
    expect(ruleBody(css, ".docxWrap :global(.docx-doc-wrapper)")).toMatch(
      /align-items:\s*flex-start/,
    );
    const page = ruleBody(
      css,
      ".docxWrap :global(.docx-doc-wrapper > section.docx-doc)",
    );
    expect(page).toMatch(/margin-left:\s*auto/);
    expect(page).toMatch(/margin-right:\s*auto/);
  });

  it("keeps the left edge of zoomed-in PDF pages reachable", () => {
    const css = readFileSync(
      resolve(__dirname, "PdfDocumentPreview.module.less"),
      "utf8",
    );
    const doc = ruleBody(css, ".pdfDocument");
    expect(doc).toMatch(/align-items:\s*flex-start/);
    expect(doc).not.toMatch(/align-items:\s*center/);
    const slot = ruleBody(css, ".pdfPageSlot");
    expect(slot).toMatch(/margin-left:\s*auto/);
    expect(slot).toMatch(/margin-right:\s*auto/);
  });
});
