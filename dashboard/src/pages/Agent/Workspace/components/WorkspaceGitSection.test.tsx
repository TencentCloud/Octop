import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

vi.mock("../../../../api/modules/git", () => ({
  gitApi: {
    status: vi.fn(),
    log: vi.fn(),
    diff: vi.fn(),
    stage: vi.fn(),
    unstage: vi.fn(),
    discard: vi.fn(),
    commit: vi.fn(),
  },
}));

vi.mock("../../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

import WorkspaceGitSection, {
  gitTreeBadges,
  useWorkspaceGit,
  type UseWorkspaceGitResult,
} from "./WorkspaceGitSection";
import type { GitStatus } from "../../../../api/modules/git";

function makeGit(status: GitStatus | null): UseWorkspaceGitResult {
  return {
    status,
    loading: false,
    error: null,
    refresh: vi.fn(),
    act: vi.fn(async () => true),
  };
}

const REPO_STATUS: GitStatus = {
  is_repo: true,
  git_available: true,
  branch: "main",
  upstream: "origin/main",
  ahead: 1,
  behind: 2,
  head_short: "eb8152a",
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

function renderSection(git: UseWorkspaceGitResult, streaming = false) {
  return render(
    <App>
      <WorkspaceGitSection
        agentId="agent-1"
        git={git}
        streaming={streaming}
        onReview={vi.fn()}
        onOpenFile={vi.fn()}
      />
    </App>,
  );
}

describe("WorkspaceGitSection", () => {
  it("shows the not-a-repo bar without expanding", () => {
    renderSection(makeGit(NOT_REPO));
    const bar = screen.getByTestId("workspace-git-bar");
    expect(bar).toBeDisabled();
    expect(screen.getByText("当前工作区不是 Git 仓库")).toBeInTheDocument();
    fireEvent.click(bar);
    expect(screen.queryByTestId("git-change-row")).not.toBeInTheDocument();
  });

  it("shows branch and change summary, then groups on expand", () => {
    renderSection(makeGit(REPO_STATUS));
    expect(screen.getByText("main ⇅1/2")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("workspace-git-bar"));

    const rows = screen.getAllByTestId("git-change-row");
    expect(rows).toHaveLength(3);
    expect(screen.getByText("MEMORY.md")).toBeInTheDocument();
    expect(screen.getByText("README.md")).toBeInTheDocument();
    expect(screen.getByText("demo.md")).toBeInTheDocument();
    expect(screen.getByText("+5")).toBeInTheDocument();
    expect(screen.getByText("−1")).toBeInTheDocument();
  });

  it("calls onReview with path and staged flag on row click", () => {
    const onReview = vi.fn();
    render(
      <App>
        <WorkspaceGitSection
          agentId="agent-1"
          git={makeGit(REPO_STATUS)}
          onReview={onReview}
          onOpenFile={vi.fn()}
        />
      </App>,
    );
    fireEvent.click(screen.getByTestId("workspace-git-bar"));
    fireEvent.click(screen.getByText("MEMORY.md"));
    expect(onReview).toHaveBeenCalledWith("MEMORY.md", true);
    fireEvent.click(screen.getByText("README.md"));
    expect(onReview).toHaveBeenCalledWith("README.md", false);
  });

  it("disables write actions while streaming", () => {
    render(
      <App>
        <WorkspaceGitSection
          agentId="agent-1"
          git={makeGit(REPO_STATUS)}
          streaming
          onReview={vi.fn()}
          onOpenFile={vi.fn()}
        />
      </App>,
    );
    fireEvent.click(screen.getByTestId("workspace-git-bar"));
    const stageButtons = screen
      .getAllByTestId("git-change-row")
      .map((row) => row.querySelectorAll("button[disabled]"));
    expect(stageButtons.some((buttons) => buttons.length > 0)).toBe(true);
  });

  it("reveals the commit box when changes are staged", () => {
    renderSection(makeGit(REPO_STATUS));
    expect(screen.queryByTestId("git-commit-input")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("workspace-git-bar"));
    expect(screen.getByTestId("git-commit-input")).toBeInTheDocument();
  });
});

describe("useWorkspaceGit", () => {
  it("fetches status once enabled and exposes refresh", async () => {
    const { gitApi } = await import("../../../../api/modules/git");
    const statusMock = gitApi.status as ReturnType<typeof vi.fn>;
    statusMock.mockResolvedValue(REPO_STATUS);

    let hook: UseWorkspaceGitResult | null = null;
    const Probe = () => {
      hook = useWorkspaceGit("agent-1", { enabled: true });
      return null;
    };
    render(<Probe />);
    await waitFor(() => {
      expect(statusMock).toHaveBeenCalledWith("agent-1");
    });
    expect(hook?.status).toEqual(REPO_STATUS);
    expect(typeof hook?.refresh).toBe("function");
  });

  it("does not fetch when disabled", async () => {
    const { gitApi } = await import("../../../../api/modules/git");
    const statusMock = gitApi.status as ReturnType<typeof vi.fn>;
    statusMock.mockClear();
    const Probe = () => {
      useWorkspaceGit("agent-1", { enabled: false });
      return null;
    };
    render(<Probe />);
    expect(statusMock).not.toHaveBeenCalled();
  });
});

describe("gitTreeBadges", () => {
  it("maps file letters and aggregates parent dirs", () => {
    const badges = gitTreeBadges(REPO_STATUS);
    expect(badges).not.toBeNull();
    expect(badges!.fileStatus.get("/README.md")).toBe("M");
    expect(badges!.fileStatus.get("/docs/demo.md")).toBe("U");
    expect(badges!.fileStatus.get("/MEMORY.md")).toBe("A");
    expect(badges!.changedDirs.has("/docs")).toBe(true);
    expect(badges!.changedDirs.has("/")).toBe(false);
  });

  it("strips trailing slashes from untracked directories", () => {
    const badges = gitTreeBadges({
      ...REPO_STATUS,
      files: [
        {
          path: ".octop/",
          status: "untracked",
          staged: false,
          added: null,
          removed: null,
        },
      ],
    });
    expect(badges!.fileStatus.get("/.octop")).toBe("U");
  });

  it("returns null when the workspace is not a repo", () => {
    expect(gitTreeBadges(NOT_REPO)).toBeNull();
    expect(gitTreeBadges(null)).toBeNull();
  });
});
