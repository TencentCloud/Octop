import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import ExpertFilePreviewList from "./ExpertFilePreviewList";

const files = [
  {
    key: "AGENTS.md",
    label: "Agent instructions",
    path: "AGENTS.md",
    content: "be nice",
  },
  { key: "FAQ.md", label: "FAQ", path: "FAQ.md", content: "q & a" },
];

describe("ExpertFilePreviewList", () => {
  it("renders one collapse row per file with inline edit action", () => {
    const onEdit = vi.fn();
    render(
      <ExpertFilePreviewList
        files={files}
        onEdit={onEdit}
        editLabel="experts.editFile"
      />,
    );

    expect(screen.getByText("Agent instructions")).toBeInTheDocument();
    expect(screen.getByText("AGENTS.md")).toBeInTheDocument();
    expect(screen.getByText("be nice")).toBeInTheDocument();

    // All previews expanded by default (single-level inline preview).
    expect(screen.getByText("q & a")).toBeVisible();

    fireEvent.click(screen.getAllByText("experts.editFile")[0]);
    expect(onEdit).toHaveBeenCalledWith("AGENTS.md");
  });

  it("renders nothing for an empty file list", () => {
    const { container } = render(<ExpertFilePreviewList files={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
