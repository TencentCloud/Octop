import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
