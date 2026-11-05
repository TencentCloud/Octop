import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DesktopChromeProvider } from "../hooks/useDesktopChrome";
import {
  MAC_TITLEBAR_HEIGHT,
  WINDOW_CONTROLS_INSET,
  type DesktopChromeStyle,
} from "../utils/desktopChrome";
import DesktopWindowDragBand from "./DesktopWindowDragBand";

const state = vi.hoisted(() => ({ fullscreen: false }));

vi.mock("../hooks/useWindowFullscreen", () => ({
  useWindowFullscreen: () => state.fullscreen,
}));

afterEach(() => {
  state.fullscreen = false;
  cleanup();
});

function renderBand(chrome: DesktopChromeStyle | null) {
  return render(
    <DesktopChromeProvider value={chrome}>
      <DesktopWindowDragBand />
    </DesktopChromeProvider>,
  );
}

describe("窗口顶部拖拽条", () => {
  it("浏览器里不出现", () => {
    const { container } = renderBand(null);
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
  });

  it("macOS 只在常规标题栏高度内可拖动，并避开交通灯", () => {
    const { container } = renderBand("mac");
    const band = container.querySelector(".octop-shell-drag-band");

    expect(band).not.toBeNull();
    expect(band).toHaveClass("octop-desktop-drag");
    expect(band).toHaveAttribute("aria-hidden", "true");
    expect(band).toHaveStyle({
      position: "fixed",
      top: "0px",
      height: `${MAC_TITLEBAR_HEIGHT}px`,
      left: `${WINDOW_CONTROLS_INSET.mac}px`,
      right: "0px",
      pointerEvents: "none",
    });
  });

  it("Windows 不在页面上放拖动条", () => {
    const { container } = renderBand("windows");
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
  });

  it("全屏时移除拖拽条", () => {
    state.fullscreen = true;
    const { container } = renderBand("mac");
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
  });
});
