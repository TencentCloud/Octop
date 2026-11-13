import { describe, expect, it } from "vitest";

import { canConvertOfficeToPdf, getDocKind, isXlsmFilename } from "./docKind";

describe("canConvertOfficeToPdf", () => {
  it("allows first-wave Office types and rejects xlsm/pdf", () => {
    expect(canConvertOfficeToPdf("a.docx")).toBe(true);
    expect(canConvertOfficeToPdf("a.doc")).toBe(true);
    expect(canConvertOfficeToPdf("a.xlsx")).toBe(true);
    expect(canConvertOfficeToPdf("a.xls")).toBe(true);
    expect(canConvertOfficeToPdf("a.pptx")).toBe(true);
    expect(canConvertOfficeToPdf("a.ppt")).toBe(true);
    expect(canConvertOfficeToPdf("a.xlsm")).toBe(false);
    expect(canConvertOfficeToPdf("a.pdf")).toBe(false);
    expect(canConvertOfficeToPdf("a.csv")).toBe(false);
  });

  it("keeps xlsm as excel for the grid viewer", () => {
    expect(isXlsmFilename("Book.xlsm")).toBe(true);
    expect(getDocKind("Book.xlsm")).toBe("excel");
  });
});
