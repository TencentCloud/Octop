import { describe, expect, it } from "vitest";
import { isolateHtmlPreview } from "./htmlPreviewDoc";

describe("isolateHtmlPreview", () => {
  it("injects the anchor guard into an existing head", () => {
    const doc = isolateHtmlPreview(
      "<html><head><title>x</title></head><body></body></html>",
    );
    expect(doc).toContain('data-octop-preview-guard="1"');
    expect(doc).toContain('<base href="about:srcdoc">');
    expect(doc.indexOf("data-octop-preview-guard")).toBeLessThan(
      doc.indexOf("<title>"),
    );
  });

  it("wraps a fragment and does not inject twice", () => {
    const once = isolateHtmlPreview('<a href="#top">top</a>');
    expect(once.startsWith("<!DOCTYPE html>")).toBe(true);
    expect(isolateHtmlPreview(once)).toBe(once);
  });
});
