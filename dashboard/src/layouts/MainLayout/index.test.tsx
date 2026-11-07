import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  chromeTopBandPx,
  WINDOW_CONTROLS_INSET,
  type DesktopChromeStyle,
} from "../../utils/desktopChrome";

const state = vi.hoisted(() => ({
  pathname: "/tasks",
  isMobile: false,
  desktopChrome: null as DesktopChromeStyle | null,
  windowFullscreen: false,
  navigate: vi.fn(),
  setChatSidebarOpen: vi.fn(),
}));

vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: state.pathname }),
  useNavigate: () => state.navigate,
  Routes: ({ children }: { children: ReactNode }) => children,
  Route: ({ path, element }: { path: string; element: ReactNode }) =>
    path === state.pathname ? element : null,
}));

vi.mock("../Sidebar", () => ({
  default: () => <aside data-testid="sidebar" />,
}));

vi.mock("../Header", () => ({
  default: () => <header data-testid="header" />,
}));

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

vi.mock("../../components/PwaUpdatePrompt", () => ({
  default: () => null,
}));

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
  useChatSidebarOpen: () => [true, state.setChatSidebarOpen],
}));

vi.mock("../../pages/Chat/chatRailEvents", () => ({
  EXPAND_CHAT_RAIL_EVENT: "octop:expand-chat-rail",
}));

vi.mock("../../hooks/useIsMobile", () => ({
  useIsMobile: () => state.isMobile,
}));

vi.mock("../../hooks/useKeyboardOffset", () => ({
  useKeyboardOffset: () => undefined,
}));

vi.mock("../../hooks/useDashboardPushToast", () => ({
  useDashboardPushToast: () => undefined,
}));

vi.mock("../../hooks/useDesktopChrome", () => ({
  useDesktopChromeStyle: () => state.desktopChrome,
}));

vi.mock("../../hooks/useWindowFullscreen", () => ({
  useWindowFullscreen: () => state.windowFullscreen,
}));

vi.mock("../../hooks/useRailShortcuts", () => ({
  useRailShortcuts: () => undefined,
}));

import MainLayout from "./index";

const platforms = [
  { name: "Web", chrome: null },
  { name: "macOS", chrome: "mac" },
  { name: "Windows", chrome: "windows" },
] as const;

const desktopPlatforms = [
  { name: "macOS", chrome: "mac" },
  { name: "Windows", chrome: "windows" },
] as const;

const routeCases = [
  { path: "/chat", page: "chat-page" },
  { path: "/tasks", page: "tasks-page" },
] as const;

function getShell(container: HTMLElement) {
  const shell = container.querySelector<HTMLElement>(".octop-window-shell");
  expect(shell).not.toBeNull();
  return shell!;
}

function getRightColumn(container: HTMLElement) {
  const content = container.querySelector<HTMLElement>(".page-container");
  const rightColumn = content?.parentElement?.parentElement;
  expect(rightColumn).toBeInstanceOf(HTMLElement);
  return rightColumn!;
}

beforeEach(() => {
  state.pathname = "/tasks";
  state.isMobile = false;
  state.desktopChrome = null;
  state.windowFullscreen = false;
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(cleanup);

describe("MainLayout 共享顶栏", () => {
  it.each(platforms)("$name 使用同一个 58px shell 顶栏", ({ chrome }) => {
    state.desktopChrome = chrome;
    const { container } = render(<MainLayout />);
    const shell = getShell(container);

    expect(shell.style.getPropertyValue("--octop-shell-top-band")).toBe("58px");
    expect(shell).toContainElement(screen.getByTestId("sidebar"));
    expect(shell).toContainElement(screen.getByTestId("tasks-page"));
    expect(screen.queryByTestId("header")).not.toBeInTheDocument();
  });

  it.each(platforms)("$name 移动布局不预留顶栏或拖拽区域", ({ chrome }) => {
    state.isMobile = true;
    state.desktopChrome = chrome;
    const { container } = render(<MainLayout />);

    expect(
      getShell(container).style.getPropertyValue("--octop-shell-top-band"),
    ).toBe("0px");
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
    expect(screen.getByTestId("header")).toBeInTheDocument();
  });

  it("Web 不渲染桌面拖拽区域", () => {
    const { container } = render(<MainLayout />);
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
  });

  it("macOS 拖拽区域限制在顶栏且避开交通灯", () => {
    state.desktopChrome = "mac";
    const { container } = render(<MainLayout />);
    const bands = container.querySelectorAll(".octop-shell-drag-band");

    expect(bands).toHaveLength(1);
    expect(bands[0]).toHaveClass("octop-desktop-drag");
    expect(bands[0]).toHaveAttribute("aria-hidden", "true");
    expect(bands[0].parentElement).toBe(getShell(container));
    expect(bands[0]).toHaveStyle({
      position: "absolute",
      top: "0px",
      height: `${chromeTopBandPx("mac")}px`,
      left: `${WINDOW_CONTROLS_INSET.mac}px`,
      right: "0px",
      pointerEvents: "none",
    });
  });

  it("Windows 页面里没有拖拽条", () => {
    state.desktopChrome = "windows";
    const { container } = render(<MainLayout />);
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
  });

  describe.each(routeCases)("$path 路由", ({ path, page }) => {
    it.each(platforms)("$name 右区不重复添加顶栏上边距", async ({ chrome }) => {
      state.pathname = path;
      state.desktopChrome = chrome;
      const { container } = render(<MainLayout />);
      await screen.findByTestId(page);

      const rightColumn = getRightColumn(container);
      expect(rightColumn).toContainElement(screen.getByTestId(page));
      expect(["", "0px"]).toContain(rightColumn.style.paddingTop);
      expect(
        getShell(container).style.getPropertyValue("--octop-shell-top-band"),
      ).toBe("58px");
    });

    it.each(desktopPlatforms)(
      "$name 切换全屏保留布局但移除拖拽区域",
      async ({ chrome }) => {
        state.pathname = path;
        state.desktopChrome = chrome;
        const { container, rerender } = render(<MainLayout />);
        await screen.findByTestId(page);
        const shell = getShell(container);
        const rightColumn = getRightColumn(container);
        const shellStyle = shell.getAttribute("style");
        const rightColumnStyle = rightColumn.getAttribute("style");
        const pageElement = screen.getByTestId(page);
        if (chrome === "windows") {
          expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
        } else {
          expect(
            container.querySelector(".octop-shell-drag-band"),
          ).not.toBeNull();
        }

        state.windowFullscreen = true;
        rerender(<MainLayout />);

        expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
        expect(getShell(container)).toBe(shell);
        expect(shell.style.getPropertyValue("--octop-shell-top-band")).toBe(
          "58px",
        );
        expect(shell).toHaveAttribute("style", shellStyle);
        expect(getRightColumn(container)).toBe(rightColumn);
        expect(rightColumn).toHaveAttribute("style", rightColumnStyle);
        expect(screen.getByTestId(page)).toBe(pageElement);
        expect(["", "0px"]).toContain(rightColumn.style.paddingTop);

        state.windowFullscreen = false;
        rerender(<MainLayout />);
        if (chrome === "windows") {
          expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
        } else {
          expect(
            container.querySelector(".octop-shell-drag-band"),
          ).not.toBeNull();
        }
        expect(shell).toHaveAttribute("style", shellStyle);
      },
    );
  });
});
