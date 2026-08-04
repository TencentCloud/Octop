import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatDockPanels from "./ChatDockPanels";

vi.mock("./ChatDockPanel", () => ({
  default: () => <div data-testid="chat-dock-panel">dock-panel</div>,
}));

const baseProps = {
  isMobile: false,
  dockMode: "right" as const,
  isResizing: false,
  panelSizes: { rightWidth: 560, bottomHeight: 380 },
  agentId: "agent-a",
  filePaths: [] as string[],
  openTabs: [{ id: "terminal" as const, kind: "terminal" as const }],
  activeTabId: "terminal" as const,
  onSelectTab: vi.fn(),
  onCloseTab: vi.fn(),
  onOpenFile: vi.fn(),
  browserEnvironment: "host" as const,
  onModeChange: vi.fn(),
  onClose: vi.fn(),
  onResizeStart: vi.fn(),
};

describe("ChatDockPanels keep-alive", () => {
  it("keeps the dock panel mounted when closed so terminal state survives", () => {
    const { rerender } = render(
      <ChatDockPanels {...baseProps} dockOpen={true} />,
    );
    expect(screen.getByTestId("chat-dock-panel")).toBeTruthy();

    rerender(<ChatDockPanels {...baseProps} dockOpen={false} />);
    expect(screen.getByTestId("chat-dock-panel")).toBeTruthy();
  });

  it("does not remount when switching layout mode", () => {
    const { rerender } = render(
      <ChatDockPanels {...baseProps} dockOpen={true} dockMode="right" />,
    );
    const first = screen.getByTestId("chat-dock-panel");

    rerender(
      <ChatDockPanels {...baseProps} dockOpen={true} dockMode="bottom" />,
    );
    expect(screen.getByTestId("chat-dock-panel")).toBe(first);
  });

  it("does not mount an empty dock when there are no tabs", () => {
    render(
      <ChatDockPanels
        {...baseProps}
        dockOpen={false}
        openTabs={[]}
        activeTabId={null}
      />,
    );
    expect(screen.queryByTestId("chat-dock-panel")).toBeNull();
  });
});
