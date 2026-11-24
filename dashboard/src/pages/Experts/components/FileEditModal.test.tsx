import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import FileEditModal from "./FileEditModal";

describe("FileEditModal", () => {
  it("edits a config file in a textarea", () => {
    render(
      <FileEditModal
        open
        filePath="/AGENTS.md"
        localValue={"# Agents\nkeep this"}
        onClose={() => {}}
        onSaved={() => {}}
        onLocalSave={() => {}}
      />,
    );

    const box = screen.getByRole("textbox");
    expect(box.tagName).toBe("TEXTAREA");
    expect(box).toHaveValue("# Agents\nkeep this");
  });
  it("adds a Markdown draft and rejects duplicate filenames", () => {
    const onCreate = vi.fn();
    const onClose = vi.fn();
    render(
      <FileEditModal
        open
        filePath={null}
        createLocalFile={{ existingNames: ["AGENTS.md"], onCreate }}
        onClose={onClose}
        onSaved={() => {}}
      />,
    );
    const filename = screen.getByLabelText("workspace.newFileName");
    const save = screen.getByRole("button", { name: "common.save" });

    fireEvent.change(filename, { target: { value: "agents" } });
    fireEvent.click(save);
    expect(screen.getByText("experts.promptFilenameExists")).toBeVisible();
    expect(onCreate).not.toHaveBeenCalled();

    fireEvent.change(filename, { target: { value: "../WORKFLOW.md" } });
    fireEvent.click(save);
    expect(screen.getByText("experts.promptFilenameInvalid")).toBeVisible();

    fireEvent.change(filename, { target: { value: "WORKFLOW" } });
    fireEvent.click(save);
    expect(onCreate).toHaveBeenCalledWith("WORKFLOW.md", "");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
