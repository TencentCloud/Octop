/**
 * Edit-mode Save used to call `values.name.trim()` even though the name field
 * is not mounted — validateFields() omits it, so the click threw and was
 * swallowed (GitHub #592).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TextDocumentEditorModal from "./TextDocumentEditorModal";

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
