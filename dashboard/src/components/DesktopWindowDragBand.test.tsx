import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DesktopChromeProvider } from "../hooks/useDesktopChrome";
import type { DesktopChromeStyle } from "../utils/desktopChrome";
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

  it.each([
    { name: "macOS", chrome: "mac" as const, left: "80px", right: "0px" },
    {
      name: "Windows",
      chrome: "windows" as const,
      left: "0px",
      right: "138px",
    },
  ])(
    "$name 只在顶部 58px 内可拖动，并避开原生按钮",
    ({ chrome, left, right }) => {
      const { container } = renderBand(chrome);
      const band = container.querySelector(".octop-shell-drag-band");

      expect(band).not.toBeNull();
      expect(band).toHaveClass("octop-desktop-drag");
      expect(band).toHaveAttribute("aria-hidden", "true");
      expect(band).toHaveStyle({
        position: "fixed",
        top: "0px",
        height: "58px",
        left,
        right,
        pointerEvents: "none",
      });
    },
  );

  it("全屏时移除拖拽条", () => {
    state.fullscreen = true;
    const { container } = renderBand("mac");
    expect(container.querySelector(".octop-shell-drag-band")).toBeNull();
  });
});
