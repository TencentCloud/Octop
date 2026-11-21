import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DesktopChromeProvider } from "../hooks/useDesktopChrome";
import LinuxWindowControls from "./LinuxWindowControls";
import WindowsAppMenu from "./WindowsAppMenu";

const state = vi.hoisted(() => ({
  fullscreen: false,
  maximized: false,
  minimize: vi.fn(),
  toggleMaximize: vi.fn(),
  close: vi.fn(),
  onMaximized: null as ((maximized: boolean) => void) | null,
}));

vi.mock("../hooks/useWindowFullscreen", () => ({
  useWindowFullscreen: () => state.fullscreen,
}));

vi.mock("../utils/desktopBridge", () => ({
  isLinuxDesktopShell: () => true,
  getDesktopBridge: () => ({
    windowControls: {
      minimize: state.minimize,
      toggleMaximize: state.toggleMaximize,
      close: state.close,
      isMaximized: async () => state.maximized,
      onMaximizedChange: (cb: (maximized: boolean) => void) => {
        state.onMaximized = cb;
        return () => {
          state.onMaximized = null;
        };
      },
    },
    windowsMenu: {
      model: async () => ({ titles: ["文件"], menus: [[]] }),
      invoke: vi.fn(),
    },
  }),
}));

afterEach(() => {
  state.fullscreen = false;
  state.maximized = false;
  state.minimize.mockClear();
  state.toggleMaximize.mockClear();
  state.close.mockClear();
  cleanup();
});

describe("Linux 方形窗口按钮", () => {
  it("画在标题栏右侧，关闭按钮单独成组", async () => {
    render(
      <DesktopChromeProvider value="windows">
        <WindowsAppMenu />
      </DesktopChromeProvider>,
    );
    const close = await screen.findByRole("button", { name: "关闭" });
    expect(close).toHaveClass("octop-linux-controls-close");
    expect(close.parentElement).toHaveClass("octop-linux-controls");
    expect(screen.getByRole("button", { name: "最小化" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "最大化" })).toBeInTheDocument();
  });

  it("方形且关闭悬停变红", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    expect(css).toMatch(
      /\.octop-linux-controls button \{[^}]*border-radius:\s*0/,
    );
    expect(css).toMatch(
      /\.octop-linux-controls-close:hover[\s\S]*background:\s*#e81123/,
    );
    expect(css).not.toMatch(
      /\.octop-linux-controls button \{[^}]*border-radius:\s*50%/,
    );
  });

  it("点击分别最小化、最大化、关闭", async () => {
    const user = userEvent.setup();
    render(<LinuxWindowControls />);
    await user.click(screen.getByRole("button", { name: "最小化" }));
    await user.click(screen.getByRole("button", { name: "最大化" }));
    await user.click(screen.getByRole("button", { name: "关闭" }));
    expect(state.minimize).toHaveBeenCalledOnce();
    expect(state.toggleMaximize).toHaveBeenCalledOnce();
    expect(state.close).toHaveBeenCalledOnce();
  });

  it("最大化后按钮改成还原", async () => {
    state.maximized = true;
    render(<LinuxWindowControls />);
    expect(
      await screen.findByRole("button", { name: "还原" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "最大化" }),
    ).not.toBeInTheDocument();
  });

  it("全屏不占那一角", () => {
    state.fullscreen = true;
    const { container } = render(<LinuxWindowControls />);
    expect(container).toBeEmptyDOMElement();
  });
});
