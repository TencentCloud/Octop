import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderAsync } from "docx-preview";
import JSZip from "jszip";
import { describe, expect, it, vi } from "vitest";

import { DOCX_RENDER_OPTIONS } from "./DocumentPreviewCore";

// pdf.js needs DOMMatrix, which jsdom lacks; the Word path never touches it.
vi.mock("react-pdf", () => ({
  Document: () => null,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

/** Smallest Word file docx-preview accepts: one paragraph on an A4 page. */
async function a4Docx(): Promise<ArrayBuffer> {
  const zip = new JSZip();
  zip.file(
    "[Content_Types].xml",
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
      "</Types>",
  );
  zip.file(
    "_rels/.rels",
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
      "</Relationships>",
  );
  zip.file(
    "word/document.xml",
    `<w:document xmlns:w="${W}"><w:body>` +
      "<w:p><w:r><w:t>Left edge</w:t></w:r></w:p>" +
      '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>' +
      "</w:body></w:document>",
  );
  return zip.generateAsync({ type: "arraybuffer" });
}

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

  it("targets the wrapper and pages docx-preview actually renders", async () => {
    const host = document.createElement("div");
    await renderAsync(await a4Docx(), host, undefined, DOCX_RENDER_OPTIONS);

    // Pages keep their real paper width (A4 = 595.3pt ≈ 794px), wider than a phone.
    const page = host.querySelector<HTMLElement>(
      ".docx-doc-wrapper > section.docx-doc",
    );
    expect(page).not.toBeNull();
    expect(page!.style.width).toBe("595.3pt");

    // docx-preview's own stylesheet is what centres (and so clips) the page.
    const injected = Array.from(host.querySelectorAll("style"))
      .map((style) => style.textContent ?? "")
      .join("\n");
    expect(injected).toMatch(
      /\.docx-doc-wrapper\s*\{[^}]*align-items:\s*center/,
    );
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
