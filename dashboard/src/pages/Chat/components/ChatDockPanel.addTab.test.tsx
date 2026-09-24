import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ChatDockPanel from "./ChatDockPanel";

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1 }),
}));

vi.mock("../../../utils/browserProfile", () => ({
  resolveBrowserProfile: () => "profile-1",
}));

vi.mock("../../../components/BrowserWorkspace", () => ({
  default: () => <div data-testid="browser-workspace" />,
}));

vi.mock("../../../components/BrowserWorkspace/ChatDockPanelShell", () => ({
  default: ({
    title,
    children,
  }: {
    title?: React.ReactNode;
    children: React.ReactNode;
  }) => (
    <div data-testid="dock-shell">
      <div data-testid="dock-title">{title}</div>
      {children}
    </div>
  ),
}));

vi.mock("../../Agent/Workspace/components/WorkspaceDrawer", () => ({
  default: () => <div data-testid="workspace-drawer" />,
}));

vi.mock("./ChatDockFileList", () => ({
  default: () => <div data-testid="file-list" />,
}));

vi.mock("./FilePanelContent", () => ({
  default: () => <div data-testid="file-panel" />,
}));

vi.mock("./KnowledgeCitationPanelContent", () => ({
  default: () => <div data-testid="knowledge-panel" />,
}));

vi.mock("./ChatDockToolUiContent", () => ({
  default: () => <div data-testid="tool-ui" />,
}));

vi.mock("../../Control/Terminal", () => ({
  default: () => <div data-testid="terminal-page" />,
}));

const baseProps = {
  mode: "right" as const,
  onModeChange: vi.fn(),
  onClose: vi.fn(),
  agentId: "agent-a",
  filePaths: [] as string[],
  openTabs: [{ id: "terminal" as const, kind: "terminal" as const }],
  activeTabId: "terminal" as const,
  onSelectTab: vi.fn(),
  onCloseTab: vi.fn(),
  onOpenFile: vi.fn(),
};

describe("ChatDockPanel add-tab menu", () => {
  it("shows a + control that opens workspace / browser / files / terminal", async () => {
    const user = userEvent.setup();
    const onOpenWorkspace = vi.fn();
    const onOpenBrowser = vi.fn();
    const onOpenFiles = vi.fn();
    const onOpenTerminal = vi.fn();

    render(
      <ChatDockPanel
        {...baseProps}
        addTab={{
          onOpenWorkspace,
          onOpenBrowser,
          onOpenFiles,
          onOpenTerminal,
        }}
      />,
    );

    const title = screen.getByTestId("dock-title");
    const addBtn = within(title).getByRole("button", { name: "添加面板" });
    await user.click(addBtn);

    await user.click(await screen.findByText("工作区"));
    expect(onOpenWorkspace).toHaveBeenCalledTimes(1);

    await user.click(addBtn);
    await user.click(await screen.findByText("文件变更"));
    expect(onOpenFiles).toHaveBeenCalledTimes(1);

    await user.click(addBtn);
    await user.click(await screen.findByText("远程浏览器"));
    expect(onOpenBrowser).toHaveBeenCalledTimes(1);

    await user.click(addBtn);
    // Terminal appears both as the open tab label and the menu item.
    const terminalItems = await screen.findAllByText("终端");
    await user.click(terminalItems[terminalItems.length - 1]!);
    expect(onOpenTerminal).toHaveBeenCalledTimes(1);
  });

  it("hides the + control when no add-tab handlers are provided", () => {
    render(<ChatDockPanel {...baseProps} />);
    expect(screen.queryByRole("button", { name: "添加面板" })).toBeNull();
  });

  it("disables workspace when the agent is not ready", async () => {
    const user = userEvent.setup();
    const onOpenWorkspace = vi.fn();

    render(
      <ChatDockPanel
        {...baseProps}
        addTab={{
          onOpenWorkspace,
          workspaceDisabled: true,
          workspaceDisabledHint: "requires running",
        }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "添加面板" }));
    const item = await screen.findByText("工作区");
    await user.click(item);
    expect(onOpenWorkspace).not.toHaveBeenCalled();
  });
});
