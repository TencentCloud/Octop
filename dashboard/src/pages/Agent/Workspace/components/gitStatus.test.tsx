import { describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

const gitApi = vi.hoisted(() => ({
  status: vi.fn(),
  log: vi.fn(),
  diff: vi.fn(),
  stage: vi.fn(),
  unstage: vi.fn(),
  discard: vi.fn(),
  commit: vi.fn(),
}));

vi.mock("../../../../api/modules/git", () => ({ gitApi }));

import {
  gitTreeBadges,
  useWorkspaceGit,
  type UseWorkspaceGitResult,
} from "./gitStatus";
import type { GitStatus } from "../../../../api/modules/git";

const REPO_STATUS: GitStatus = {
  is_repo: true,
  git_available: true,
  branch: "main",
  upstream: null,
  ahead: 0,
  behind: 0,
  head_short: "abc1234",
  files: [
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
    {
      path: ".octop/",
      status: "untracked",
      staged: false,
      added: null,
      removed: null,
    },
  ],
  added: 7,
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

describe("useWorkspaceGit", () => {
  it("fetches status once enabled and exposes refresh", async () => {
    gitApi.status.mockResolvedValue(REPO_STATUS);
    let hook: UseWorkspaceGitResult | null = null;
    const Probe = () => {
      hook = useWorkspaceGit("agent-1", { enabled: true });
      return null;
    };
    render(<Probe />);
    await waitFor(() => {
      expect(gitApi.status).toHaveBeenCalledWith("agent-1");
    });
    expect(hook?.status).toEqual(REPO_STATUS);
  });

  it("does not fetch when disabled", () => {
    gitApi.status.mockClear();
    const Probe = () => {
      useWorkspaceGit("agent-1", { enabled: false });
      return null;
    };
    render(<Probe />);
    expect(gitApi.status).not.toHaveBeenCalled();
  });
});

describe("gitTreeBadges", () => {
  it("maps file letters and aggregates parent dirs", () => {
    const badges = gitTreeBadges(REPO_STATUS);
    expect(badges).not.toBeNull();
    expect(badges!.fileStatus.get("/README.md")).toBe("M");
    expect(badges!.fileStatus.get("/docs/demo.md")).toBe("U");
    expect(badges!.fileStatus.get("/.octop")).toBe("U");
    expect(badges!.changedDirs.has("/docs")).toBe(true);
  });

  it("returns null for non-repo or missing status", () => {
    expect(gitTreeBadges(NOT_REPO)).toBeNull();
    expect(gitTreeBadges(null)).toBeNull();
  });
});
