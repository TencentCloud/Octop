import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "antd";

import GitChangeList from "./GitChangeList";
import type { GitStatus } from "../../../api/modules/git";

const STATUS: GitStatus = {
  is_repo: true,
  git_available: true,
  branch: "main",
  upstream: "origin/main",
  ahead: 1,
  behind: 0,
  head_short: "a817df60",
  files: [
    { path: "MEMORY.md", status: "added", staged: true, added: 3, removed: 0 },
    {
      path: "README.md",
      status: "modified",
      staged: false,
      added: 5,
      removed: 1,
    },
    {
      path: "docs/demo.md",
      status: "untracked",
      staged: false,
      added: 2,
      removed: null,
    },
  ],
  added: 10,
  removed: 1,
};

function renderList(overrides?: Partial<Parameters<typeof GitChangeList>[0]>) {
  return render(
    <App>
      <GitChangeList
        status={STATUS}
        onSelect={vi.fn()}
        onOpenFile={vi.fn()}
        onStage={vi.fn()}
        onUnstage={vi.fn()}
        onDiscard={vi.fn()}
        {...overrides}
      />
    </App>,
  );
}

describe("GitChangeList", () => {
  it("renders staged, changes and untracked groups with line stats", () => {
    renderList();
    const rows = screen.getAllByTestId("git-change-row");
    expect(rows).toHaveLength(3);
    expect(screen.getByText("MEMORY.md")).toBeInTheDocument();
    expect(screen.getByText("README.md")).toBeInTheDocument();
    expect(screen.getByText("demo.md")).toBeInTheDocument();
    expect(screen.getByText("+5")).toBeInTheDocument();
    expect(screen.getByText("−1")).toBeInTheDocument();
  });

  it("calls onSelect with path and staged flag on row click", () => {
    const onSelect = vi.fn();
    renderList({ onSelect });
    fireEvent.click(screen.getByText("MEMORY.md"));
    expect(onSelect).toHaveBeenCalledWith("MEMORY.md", true);
    fireEvent.click(screen.getByText("README.md"));
    expect(onSelect).toHaveBeenCalledWith("README.md", false);
  });

  it("marks the selected row", () => {
    renderList({ selectedPath: "README.md", selectedStaged: false });
    const row = screen
      .getAllByTestId("git-change-row")
      .find((el) => el.textContent?.includes("README.md"));
    expect(row?.getAttribute("data-staged")).toBe("false");
  });

  it("disables write actions while streaming", () => {
    renderList({ streaming: true });
    const rows = screen.getAllByTestId("git-change-row");
    expect(
      rows.some((row) => row.querySelectorAll("button[disabled]").length > 0),
    ).toBe(true);
  });

  it("shows the empty state without changes", () => {
    renderList({ status: { ...STATUS, files: [] } });
    expect(screen.getByTestId("git-empty")).toBeInTheDocument();
    expect(screen.getByText("没有未提交的更改")).toBeInTheDocument();
  });
});
