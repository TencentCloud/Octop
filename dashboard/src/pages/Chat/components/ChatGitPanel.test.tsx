import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

const gitApi = vi.hoisted(() => ({
  status: vi.fn(),
  log: vi.fn(),
  diff: vi.fn(),
  stage: vi.fn(),
  unstage: vi.fn(),
  discard: vi.fn(),
  commit: vi.fn(),
  commitAdvanced: vi.fn(),
  generateMessage: vi.fn(),
  push: vi.fn(),
  history: vi.fn(),
}));

vi.mock("../../../api/modules/git", () => ({ gitApi }));

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

import ChatGitPanel from "./ChatGitPanel";
import type { GitStatus } from "../../../api/modules/git";

const REPO_STATUS: GitStatus = {
  is_repo: true,
  git_available: true,
  branch: "main",
  upstream: "origin/main",
  ahead: 1,
  behind: 0,
  head_short: "a817df60",
  files: [
    {
      path: "README.md",
      status: "modified",
      staged: false,
      added: 5,
      removed: 1,
    },
  ],
  added: 5,
  removed: 1,
};

const NOT_REPO: GitStatus = {
  is_repo: false,
  git_available: true,
  branch: null,
  upstream: null,
  ahead: 0,
  behind: 0,
  head_short: null,
  files: [],
  added: 0,
  removed: 0,
};

function renderPanel() {
  return render(
    <App>
      <ChatGitPanel agentId="agent-1" />
    </App>,
  );
}

describe("ChatGitPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the not-a-repo empty state without requesting diffs", async () => {
    gitApi.status.mockResolvedValue(NOT_REPO);
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("git-panel-empty")).toBeInTheDocument();
    });
    expect(screen.getByText("当前工作区不是 Git 仓库")).toBeInTheDocument();
    expect(gitApi.diff).not.toHaveBeenCalled();
  });

  it("renders header summary and selects a file diff on row click", async () => {
    gitApi.status.mockResolvedValue(REPO_STATUS);
    gitApi.diff.mockResolvedValue({
      path: "README.md",
      diff: "@@ -1 +1 @@\n-old\n+new\n",
      truncated: false,
    });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("git-panel-summary")).toHaveTextContent(
        "1 个文件变更",
      );
    });
    expect(screen.getByTestId("git-tools-changes")).toHaveTextContent("+5");
    expect(screen.getByTestId("git-tools-changes")).toHaveTextContent("−1");
    expect(screen.getByText("main ⇅1/0")).toBeInTheDocument();
    expect(screen.getByTestId("git-diff-empty")).toBeInTheDocument();

    fireEvent.click(screen.getByText("README.md"));
    await waitFor(() => {
      expect(screen.getByText("+new")).toBeInTheDocument();
    });
    expect(gitApi.diff).toHaveBeenCalledWith("agent-1", "README.md", false);
  });

  it("opens the commit dialog and commits through it", async () => {
    gitApi.status.mockResolvedValue({
      ...REPO_STATUS,
      files: [
        { path: "a.md", status: "added", staged: true, added: 1, removed: 0 },
      ],
    });
    gitApi.commitAdvanced.mockResolvedValue({
      commit: "abc1234",
      message: "test commit",
      pushed: false,
    });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("git-commit-open")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("git-commit-open"));
    const input = await screen.findByTestId("git-commit-dialog-input");
    fireEvent.change(input, { target: { value: "test commit" } });
    fireEvent.click(screen.getByTestId("git-action-commit"));
    await waitFor(() => {
      expect(gitApi.commitAdvanced).toHaveBeenCalledWith("agent-1", {
        message: "test commit",
        include_unstaged: true,
        push: false,
      });
    });
  });

  it("opens the commit graph from the history row", async () => {
    gitApi.status.mockResolvedValue(REPO_STATUS);
    const onOpenHistory = vi.fn();
    render(
      <App>
        <ChatGitPanel agentId="agent-1" onOpenHistory={onOpenHistory} />
      </App>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("git-history-open")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("git-history-open"));
    expect(onOpenHistory).toHaveBeenCalled();
  });
});
