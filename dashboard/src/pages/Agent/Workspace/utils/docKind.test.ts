import { describe, expect, it } from "vitest";
import { getDocKind, getEditableDocLanguage, isEditableDoc } from "./docKind";

describe("isEditableDoc", () => {
  it("accepts .docx in any case and nesting", () => {
    expect(isEditableDoc("report.docx")).toBe(true);
    expect(isEditableDoc("REPORT.DOCX")).toBe(true);
    expect(isEditableDoc("/work/dir/sub/report.docx")).toBe(true);
  });

  it("rejects other extensions and extension-less paths", () => {
    expect(isEditableDoc("report.doc")).toBe(false);
    expect(isEditableDoc("report.pdf")).toBe(false);
    expect(isEditableDoc("report.md")).toBe(false);
    expect(isEditableDoc("report")).toBe(false);
  });
});

describe("getEditableDocLanguage", () => {
  it("maps editable docs to markdown", () => {
    expect(getEditableDocLanguage("/a.docx")).toBe("markdown");
  });

  it("returns null for non-editable files", () => {
    expect(getEditableDocLanguage("/a.doc")).toBeNull();
    expect(getEditableDocLanguage("/a.md")).toBeNull();
  });
});

describe("getDocKind (regression)", () => {
  it("still classifies word docs as word", () => {
    expect(getDocKind("/a.docx")).toBe("word");
    expect(getDocKind("/a.doc")).toBe("word");
  });
});
