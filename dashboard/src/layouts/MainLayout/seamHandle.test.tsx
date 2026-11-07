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

import styles from "../../components/RailEdgeControl.module.less";
import MainLayout from "./index";

beforeEach(() => {
  state.pathname = "/chat";
  state.chatSidebarOpen = true;
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(cleanup);

describe("左侧导航接缝", () => {
  it("列表展开时只在导航右侧放收起导航的竖线按钮", () => {
    render(<MainLayout />);

    const button = screen.getByRole("button", { name: "收起导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    expect(button).not.toHaveClass(styles.btnBefore);
    expect(
      screen.queryByRole("button", { name: "展开对话历史" }),
    ).not.toBeInTheDocument();
  });

  it("列表收起时，收起导航仍是右侧竖线上的按钮", async () => {
    state.chatSidebarOpen = false;
    const user = userEvent.setup();
    render(<MainLayout />);

    const collapseNav = screen.getByRole("button", { name: "收起导航栏" });
    expect(collapseNav).not.toHaveClass(styles.btnBefore);
    expect(collapseNav.querySelector("svg")?.getAttribute("class")).toContain(
      "chevron-left",
    );
    expect(
      screen.queryByRole("button", { name: "展开对话历史" }),
    ).not.toBeInTheDocument();

    await user.click(collapseNav);
    expect(
      screen.getByRole("button", { name: "展开导航栏" }),
    ).toBeInTheDocument();
  });

  it("不在对话路由上时不提供展开对话历史", () => {
    state.pathname = "/tasks";
    state.chatSidebarOpen = false;
    render(<MainLayout />);
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "收起导航栏" }),
    ).toBeInTheDocument();
  });
});
