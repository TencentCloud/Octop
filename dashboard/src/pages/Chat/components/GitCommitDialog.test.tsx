import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

const gitApi = vi.hoisted(() => ({
  generateMessage: vi.fn(),
  commitAdvanced: vi.fn(),
  push: vi.fn(),
}));

vi.mock("../../../api/modules/git", () => ({ gitApi }));

import GitCommitDialog from "./GitCommitDialog";
import type { GitStatus } from "../../../api/modules/git";

const STATUS: GitStatus = {
  is_repo: true,
  git_available: true,
  branch: "develop",
  upstream: "origin/develop",
  ahead: 1,
  behind: 0,
  head_short: "abc1234",
  files: [
    { path: "a.md", status: "added", staged: true, added: 3, removed: 0 },
    { path: "b.md", status: "modified", staged: false, added: 2, removed: 1 },
  ],
  added: 5,
  removed: 1,
};

function renderDialog(onDone = vi.fn(), onClose = vi.fn()) {
  render(
    <App>
      <GitCommitDialog
        open
        agentId="agent-1"
        status={STATUS}
        onClose={onClose}
        onDone={onDone}
      />
    </App>,
  );
  return { onDone, onClose };
}

describe("GitCommitDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("generates a message when the field is empty before committing", async () => {
    gitApi.generateMessage.mockResolvedValue({ message: "feat: add a" });
    gitApi.commitAdvanced.mockResolvedValue({
      commit: "abc1234",
      message: "feat: add a",
      pushed: false,
    });
    const { onDone, onClose } = renderDialog();

    fireEvent.click(screen.getByTestId("git-action-commit"));
    await waitFor(() => {
      expect(gitApi.generateMessage).toHaveBeenCalledWith("agent-1", true);
    });
    await waitFor(() => {
      expect(gitApi.commitAdvanced).toHaveBeenCalledWith("agent-1", {
        message: "feat: add a",
        include_unstaged: true,
        push: false,
      });
    });
    expect(onDone).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("can exclude unstaged changes and commit and push", async () => {
    gitApi.commitAdvanced.mockResolvedValue({
      commit: "abc1234",
      message: "fix: only staged",
      pushed: true,
    });
    renderDialog();

    fireEvent.click(screen.getByTestId("git-commit-include-unstaged"));
    fireEvent.change(screen.getByTestId("git-commit-dialog-input"), {
      target: { value: "fix: only staged" },
    });
    fireEvent.click(screen.getByTestId("git-action-commit-push"));
    await waitFor(() => {
      expect(gitApi.commitAdvanced).toHaveBeenCalledWith("agent-1", {
        message: "fix: only staged",
        include_unstaged: false,
        push: true,
      });
    });
  });

  it("pushes without committing", async () => {
    gitApi.push.mockResolvedValue({
      branch: "develop",
      remote: "origin",
      upstream: "origin/develop",
      set_upstream: false,
      output: "",
    });
    renderDialog();
    fireEvent.click(screen.getByTestId("git-action-push"));
    await waitFor(() => {
      expect(gitApi.push).toHaveBeenCalledWith("agent-1");
    });
  });

  it("disables commit when nothing is selected", () => {
    render(
      <App>
        <GitCommitDialog
          open
          agentId="agent-1"
          status={{ ...STATUS, files: [] }}
          onClose={vi.fn()}
          onDone={vi.fn()}
        />
      </App>,
    );
    expect(screen.getByTestId("git-action-commit")).toBeDisabled();
  });
});
