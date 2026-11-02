import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatSidebarPanel from "./ChatSidebarPanel";

vi.mock("./SessionList", () => ({
  default: () => <div data-testid="session-list" />,
}));

const baseProps = {
  isMobile: false,
  sidebarWidth: 248,
  agents: [],
  sessions: [],
  activeThreadId: null,
  resolvedAgentId: null,
  sessionsHasMore: false,
  sessionsLoadingMore: false,
  onLoadMoreSessions: () => undefined,
  onFetchAllSessions: () => undefined,
  onSelectSession: () => undefined,
  onAgentSelect: () => undefined,
  onNewChatWithAgent: () => undefined,
  onDeleteSession: () => undefined,
  onRenameSession: () => undefined,
  onPinSession: () => undefined,
  onForkSession: () => undefined,
  onSidebarOpenChange: () => undefined,
  layoutRail: true,
};

describe("ChatSidebarPanel edge", () => {
  it("拖拽落在展开列表右侧竖线的上半段", () => {
    const onSidebarResizeStart = vi.fn();
    render(
      <ChatSidebarPanel
        {...baseProps}
        sidebarOpen
        onSidebarResizeStart={onSidebarResizeStart}
      />,
    );

    const grip = screen.getByRole("separator", { name: "调整侧栏宽度" });
    fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientX: 40 });
    expect(onSidebarResizeStart).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "收起对话历史" }),
    ).toBeInTheDocument();
  });

  it("列表收起时右侧竖线不提供展开，展开在对话行按钮上", () => {
    render(
      <ChatSidebarPanel
        {...baseProps}
        sidebarOpen={false}
        onSidebarResizeStart={() => undefined}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "展开对话历史" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
  });
});
