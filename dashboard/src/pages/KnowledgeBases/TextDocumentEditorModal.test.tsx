/**
 * Edit mode mounts the filename field too (so a document can be renamed while
 * editing). Saving used to read `values.name` even when that field was never
 * mounted, which threw and was swallowed (GitHub #592); an unchanged
 * content+name pair must still close without calling the API.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TextDocumentEditorModal from "./TextDocumentEditorModal";

describe("<TextDocumentEditorModal />", () => {
  it("submits edit-mode content and keeps the current filename", async () => {
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

  it("closes without submitting when content and filename are unchanged", async () => {
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

  it("submits when edit-mode filename changes even if content is unchanged", async () => {
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

    const nameInput = screen.getByPlaceholderText(
      "knowledgeBases.filenamePlaceholder",
    );
    await user.clear(nameInput);
    await user.type(nameInput, "腾讯地图.md");

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "腾讯地图.md",
      format: "md",
      content: "same body",
    });
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("blocks submit when the edit-mode filename is emptied", async () => {
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

    const nameInput = screen.getByPlaceholderText(
      "knowledgeBases.filenamePlaceholder",
    );
    await user.clear(nameInput);
    await user.type(nameInput, "   ");

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(
        screen.getByText("knowledgeBases.filenameRequired"),
      ).toBeInTheDocument(),
    );
    expect(onSubmit).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });
});
