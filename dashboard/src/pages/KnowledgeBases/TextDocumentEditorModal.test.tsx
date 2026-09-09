/**
 * Edit-mode Save used to call `values.name.trim()` even though the name field
 * is not mounted — validateFields() omits it, so the click threw and was
 * swallowed (GitHub #592).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TextDocumentEditorModal, {
  canDownloadKnowledgeOriginal,
  canPreviewKnowledgeDocument,
  canRichPreviewKnowledgeDocument,
} from "./TextDocumentEditorModal";

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
});

describe("<TextDocumentEditorModal />", () => {
  it("submits edit-mode content without a mounted name field", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <TextDocumentEditorModal
        open
        mode="edit"
        initialName="高德地图.md"
        initialFormat="md"
        initialContent={"line1\n"}
        onCancel={() => undefined}
        onSubmit={onSubmit}
      />,
    );

    const editor = screen.getByPlaceholderText(
      "knowledgeBases.fileContentPlaceholder",
    );
    await user.clear(editor);
    await user.type(editor, "updated body");

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "高德地图.md",
      format: "md",
      content: "updated body",
    });
  });

  it("closes without submitting when edit-mode content is unchanged", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <TextDocumentEditorModal
        open
        mode="edit"
        initialName="高德地图.md"
        initialFormat="md"
        initialContent={"same body\n"}
        onCancel={onCancel}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(onCancel).toHaveBeenCalledTimes(1));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits when edit-mode content changes by a single character", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <TextDocumentEditorModal
        open
        mode="edit"
        initialName="高德地图.md"
        initialFormat="md"
        initialContent={"same body"}
        onCancel={onCancel}
        onSubmit={onSubmit}
      />,
    );

    const editor = screen.getByPlaceholderText(
      "knowledgeBases.fileContentPlaceholder",
    );
    await user.type(editor, "!");

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "高德地图.md",
      format: "md",
      content: "same body!",
    });
    expect(onCancel).not.toHaveBeenCalled();
  });
});
