import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DesktopChromeProvider } from "../hooks/useDesktopChrome";
import type { DesktopChromeStyle } from "../utils/desktopChrome";
import WindowsAppMenu from "./WindowsAppMenu";

const state = vi.hoisted(() => ({
  fullscreen: false,
  invoke: vi.fn(),
  model: vi.fn(async () => ({
    titles: ["文件", "编辑", "视图", "帮助"],
    menus: [
      [
        {
          kind: "command" as const,
          id: "close",
          label: "关闭",
          accelerator: "Ctrl+W",
        },
        { kind: "separator" as const },
        {
          kind: "command" as const,
          id: "quit",
          label: "退出",
          accelerator: null,
        },
      ],
      [
        {
          kind: "command" as const,
          id: "undo",
          label: "撤销",
          accelerator: "Ctrl+Z",
        },
      ],
      [],
      [
        {
          kind: "command" as const,
          id: "about",
          label: "关于 Octop",
          accelerator: null,
        },
      ],
    ],
  })),
  hasMenu: true,
}));

vi.mock("../hooks/useWindowFullscreen", () => ({
  useWindowFullscreen: () => state.fullscreen,
}));

vi.mock("../utils/desktopBridge", () => ({
  isLinuxDesktopShell: () => false,
  getDesktopBridge: () =>
    state.hasMenu
      ? { windowsMenu: { model: state.model, invoke: state.invoke } }
      : {},
}));

afterEach(() => {
  state.fullscreen = false;
  state.hasMenu = true;
  state.invoke.mockClear();
  cleanup();
});

function renderMenu(chrome: DesktopChromeStyle | null) {
  return render(
    <DesktopChromeProvider value={chrome}>
      <WindowsAppMenu />
    </DesktopChromeProvider>,
  );
}

describe("Windows 标题栏菜单", () => {
  it("在标题栏左侧画出四个菜单", async () => {
    renderMenu("windows");
    expect(
      await screen.findByRole("menuitem", { name: "文件" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "编辑" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "视图" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "帮助" })).toBeInTheDocument();
  });

  it("点击后在页面里展开子菜单，并执行选中的命令", async () => {
    const user = userEvent.setup();
    renderMenu("windows");
    await user.click(await screen.findByRole("menuitem", { name: "文件" }));
    expect(screen.getByRole("menuitem", { name: /关闭/ })).toBeInTheDocument();
    expect(screen.getByText("Ctrl+W")).toBeInTheDocument();
    expect(screen.getByRole("separator")).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "退出" }));
    expect(state.invoke).toHaveBeenCalledWith("quit");
    expect(
      screen.queryByRole("menuitem", { name: "退出" }),
    ).not.toBeInTheDocument();
  });

  it("macOS 和浏览器不画这排菜单", () => {
    const { container, rerender } = renderMenu("mac");
    expect(container.querySelector(".octop-win-menu")).toBeNull();
    rerender(
      <DesktopChromeProvider value={null}>
        <WindowsAppMenu />
      </DesktopChromeProvider>,
    );
    expect(container.querySelector(".octop-win-menu")).toBeNull();
  });

  it("占一整行，并把页面顶下去", async () => {
    renderMenu("windows");
    await screen.findByRole("menuitem", { name: "文件" });
    const bar = document.querySelector(".octop-win-menu");
    expect(bar).toHaveClass("octop-desktop-drag");
    expect(document.documentElement.dataset.octopCaptionRow).toBe("");
    expect(
      document.documentElement.style.getPropertyValue("--octop-caption-row"),
    ).toBe("32px");
  });

  it("全屏仍画出菜单栏", async () => {
    state.fullscreen = true;
    renderMenu("windows");
    expect(
      await screen.findByRole("menuitem", { name: "文件" }),
    ).toBeInTheDocument();
    expect(document.documentElement.dataset.octopCaptionRow).toBe("");
    expect(
      document.documentElement.style.getPropertyValue("--octop-caption-row"),
    ).toBe("32px");
  });
});
