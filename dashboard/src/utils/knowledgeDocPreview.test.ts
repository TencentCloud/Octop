import { describe, expect, it } from "vitest";

import {
  canDownloadKnowledgeOriginal,
  canPreviewKnowledgeDocument,
  canRichPreviewKnowledgeDocument,
  isRichPreviewFilename,
} from "./knowledgeDocPreview";

describe("canPreviewKnowledgeDocument", () => {
  it("allows rich and text preview types", () => {
    expect(canPreviewKnowledgeDocument({ filename: "a.pdf" })).toBe(true);
    expect(canPreviewKnowledgeDocument({ filename: "a.docx" })).toBe(true);
    expect(canPreviewKnowledgeDocument({ filename: "a.xlsx" })).toBe(true);
    expect(canPreviewKnowledgeDocument({ filename: "a.md" })).toBe(true);
    expect(canPreviewKnowledgeDocument({ filename: "a.csv" })).toBe(true);
  });

  it("rejects directories and unknown binaries", () => {
    expect(canPreviewKnowledgeDocument({ is_dir: true, filename: "d" })).toBe(
      false,
    );
    expect(canPreviewKnowledgeDocument({ filename: "photo.bin" })).toBe(false);
    expect(canPreviewKnowledgeDocument({ filename: "archive.zip" })).toBe(
      false,
    );
  });
});

describe("canDownloadKnowledgeOriginal", () => {
  it("allows uploaded office/pdf originals", () => {
    expect(canDownloadKnowledgeOriginal({ filename: "a.pdf" })).toBe(true);
    expect(canDownloadKnowledgeOriginal({ filename: "a.docx" })).toBe(true);
  });

  it("allows in-app md/txt notes when the file exists on disk", () => {
    expect(canDownloadKnowledgeOriginal({ filename: "note.md" })).toBe(true);
    expect(
      canDownloadKnowledgeOriginal({
        filename: "note.txt",
        content_type: "text/plain",
      }),
    ).toBe(true);
  });

  it("hides download when the original is missing", () => {
    expect(
      canDownloadKnowledgeOriginal({
        filename: "a.pdf",
        has_original: false,
      }),
    ).toBe(false);
    expect(
      canDownloadKnowledgeOriginal({
        filename: "note.md",
        has_original: false,
      }),
    ).toBe(false);
  });
});

describe("canRichPreviewKnowledgeDocument", () => {
  it("requires original and a supported office/pdf extension", () => {
    expect(canRichPreviewKnowledgeDocument({ filename: "a.pdf" })).toBe(true);
    expect(canRichPreviewKnowledgeDocument({ filename: "a.docx" })).toBe(true);
    expect(canRichPreviewKnowledgeDocument({ filename: "a.doc" })).toBe(true);
    expect(canRichPreviewKnowledgeDocument({ filename: "a.xls" })).toBe(true);
    expect(canRichPreviewKnowledgeDocument({ filename: "a.ppt" })).toBe(false);
    expect(
      canRichPreviewKnowledgeDocument({
        filename: "a.pdf",
        has_original: false,
      }),
    ).toBe(false);
  });

  it("treats unknown has_original as attemptable for citation preview", () => {
    expect(isRichPreviewFilename("a.pdf")).toBe(true);
    expect(canRichPreviewKnowledgeDocument({ filename: "a.pdf" })).toBe(true);
  });
});
