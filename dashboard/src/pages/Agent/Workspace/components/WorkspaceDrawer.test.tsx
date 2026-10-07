import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

const TREE_COLLAPSED_KEY = "octop:workspace-drawer-tree-collapsed";

vi.mock("../../../../api/request", () => ({
  request: vi.fn(async () => []),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));

vi.mock("../../../../api/modules/workspace", () => ({
  workspaceApi: {
    deleteWorkspaceFile: vi.fn(),
    mkdirWorkspaceDir: vi.fn(),
    createWorkspaceFile: vi.fn(),
    moveWorkspaceFile: vi.fn(),
    downloadWorkspaceArchive: vi.fn(),
    importWorkspaceArchive: vi.fn(),
  },
}));

vi.mock("../../../../context/AgentContext", () => ({
  useAgent: () => ({
    agents: [{ agent_id: "agent-1", name: "Demo", state: "running" }],
  }),
}));

vi.mock("../../../../hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("../../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

vi.mock("./FileViewer", () => ({
  default: () => <div data-testid="file-viewer" />,
}));

import WorkspaceDrawer from "./WorkspaceDrawer";

function renderEmbedded() {
  return render(
    <App>
      <WorkspaceDrawer
        agentId="agent-1"
        open
        onClose={() => undefined}
        embedded
      />
    </App>,
  );
}

describe("WorkspaceDrawer embedded tree", () => {
  beforeEach(() => {
    localStorage.removeItem(TREE_COLLAPSED_KEY);
  });

  it("hides the folder tree by default in the chat dock", async () => {
    renderEmbedded();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "显示目录树" }),
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("tree")).not.toBeInTheDocument();
  });

  it("keeps the folder tree visible when the user last expanded it", async () => {
    localStorage.setItem(TREE_COLLAPSED_KEY, "0");
    renderEmbedded();

    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: "收起目录树" }),
    ).toBeInTheDocument();
  });
});
