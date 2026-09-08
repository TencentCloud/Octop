import { describe, expect, it } from "vitest";
import { clampAbsurdDocxCssLengths } from "./DocumentPreviewCore";

describe("clampAbsurdDocxCssLengths", () => {
  it("zeros out overflow-scale min-height / line-height from corrupt DOCX spacing", () => {
    const style =
      "margin-top: 0pt; margin-bottom: 0pt; min-height: 2.68435e+07pt; line-height: 2.68435e+07pt;";
    expect(clampAbsurdDocxCssLengths(style)).toBe(
      "margin-top: 0pt; margin-bottom: 0pt; min-height: 0pt; line-height: 0pt;",
    );
  });

  it("leaves normal page lengths alone", () => {
    const style = "width: 595.3pt; height: 841.9pt; margin-top: 12pt;";
    expect(clampAbsurdDocxCssLengths(style)).toBe(style);
  });

  it("ignores styles without length properties we care about", () => {
    const style = "color: red; display: block;";
    expect(clampAbsurdDocxCssLengths(style)).toBe(style);
  });
});
