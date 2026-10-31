import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  pathname: "/chat",
  chatSidebarOpen: true,
  setChatSidebarOpen: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: state.pathname }),
  useNavigate: () => state.navigate,
  Routes: ({ children }: { children: ReactNode }) => children,
  Route: ({ path, element }: { path: string; element: ReactNode }) =>
    path === state.pathname ? element : null,
}));

vi.mock("../Sidebar", () => ({ default: () => <aside /> }));

vi.mock("../../components/PageLoading", () => ({
  default: () => <div data-testid="page-loading" />,
}));

vi.mock("../../context/ServiceRestartContext", () => ({
  ServiceRestartProvider: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("../../context/BackupOperationContext", () => ({
  BackupOperationProvider: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("../../context/LayoutModeContext", () => ({
  useLayoutMode: () => ({ layoutMode: "classic" }),
}));

vi.mock("../../components/PwaUpdatePrompt", () => ({ default: () => null }));
vi.mock("../../components/PwaInstallPrompt", () => ({
  PwaAutoPrompt: () => null,
}));
vi.mock("../../components/RequirePermission", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("../../utils/permissions", () => ({
  routeNeedsPermission: () => false,
}));

vi.mock("../../routes", () => ({
  routeConfigs: [
    { path: "/chat", useWrapper: true },
    { path: "/tasks", element: <div data-testid="tasks-page" /> },
  ],
  resolveSelectedKey: (path: string) => path.slice(1),
  FULLSCREEN_PATHS: new Set(["/chat"]),
  MOBILE_FULLSCREEN_PATHS: new Set(["/chat"]),
  SELF_HEADER_PATHS: new Set(["/chat"]),
  isWorkbenchPath: () => false,
}));

vi.mock("../../pages/Chat", () => ({
  default: () => <div data-testid="chat-page" />,
}));

vi.mock("../../pages/Control/Workbench", () => ({
  default: () => <div data-testid="workbench-page" />,
}));

vi.mock("../../pages/Chat/hooks/useChatSidebarState", () => ({
  useChatSidebarOpen: () => [state.chatSidebarOpen, state.setChatSidebarOpen],
}));

vi.mock("../../pages/Chat/chatRailEvents", () => ({
  EXPAND_CHAT_RAIL_EVENT: "octop:expand-chat-rail",
}));

vi.mock("../../hooks/useIsMobile", () => ({ useIsMobile: () => false }));
vi.mock("../../hooks/useKeyboardOffset", () => ({
  useKeyboardOffset: () => undefined,
}));
vi.mock("../../hooks/useDashboardPushToast", () => ({
  useDashboardPushToast: () => undefined,
}));
vi.mock("../../hooks/useDesktopChrome", () => ({
  useDesktopChromeStyle: () => null,
}));
vi.mock("../../hooks/useWindowFullscreen", () => ({
  useWindowFullscreen: () => false,
}));
vi.mock("../../hooks/useRailShortcuts", () => ({
  useRailShortcuts: () => undefined,
}));

import MainLayout from "./index";

beforeEach(() => {
  state.pathname = "/chat";
  state.chatSidebarOpen = true;
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(cleanup);

/**
 * Second seam: the conversation list folds from the line it shares with the
 * main column. The handle hangs off the rail's own mount point, not out of
 * either column's header — collapsing the list therefore leaves it where the
 * new edge is, with the arrow flipped.
 */
describe("对话列表与主对话框之间的接缝手柄", () => {
  it("列表展开时挂在容器接缝上，点一下收起", async () => {
    const user = userEvent.setup();
    render(<MainLayout />);

    const button = screen.getByRole("button", { name: "收起对话历史" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+Shift+B");
    expect(button.getAttribute("title")).toMatch(/收起对话历史 \(.+B\)/);
    // `left: 100%` of this box is the seam; that is why the handle follows it.
    expect(document.getElementById("octop-chat-history-rail")).toContainElement(
      button,
    );

    await user.click(button);
    expect(state.setChatSidebarOpen).toHaveBeenCalledWith(false);
  });

  it("列表收起后仍在那条接缝上，点一下把两层栏一起唤回", async () => {
    state.chatSidebarOpen = false;
    const user = userEvent.setup();
    render(<MainLayout />);

    const button = screen.getByRole("button", { name: "展开对话历史" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    // The broadcast is what re-opens a collapsed nav along with the list.
    expect(state.setChatSidebarOpen).toHaveBeenCalledWith(true);
  });

  it("不在对话路由上时不挂第二边界", () => {
    state.pathname = "/tasks";
    render(<MainLayout />);
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).toBeNull();
  });
});
