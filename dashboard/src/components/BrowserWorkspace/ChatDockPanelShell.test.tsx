import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DesktopChromeProvider } from "../../hooks/useDesktopChrome";
import {
  DOCK_WINDOW_CONTROLS_PAD_PX,
  WINDOW_CONTROLS_SPACER_ATTR,
  resolveDesktopChromeStyle,
  windowControlsInset,
} from "../../utils/desktopChrome";
import ChatDockPanelShell from "./ChatDockPanelShell";

const baseProps = {
  onModeChange: vi.fn(),
  onClose: vi.fn(),
  children: <div>dock-body</div>,
};

function renderShell(
  mode: "right" | "popup" | "bottom",
  chrome: "mac" | "windows" | null,
) {
  return render(
    <DesktopChromeProvider value={chrome}>
      <ChatDockPanelShell {...baseProps} mode={mode} />
    </DesktopChromeProvider>,
  );
}

function expectedDockSpacer(chrome: "mac" | "windows"): string {
  return `${
    windowControlsInset(chrome, "end") - DOCK_WINDOW_CONTROLS_PAD_PX
  }px`;
}

function spacerWidth(container: HTMLElement): string | undefined {
  const el = container.querySelector(
    `[${WINDOW_CONTROLS_SPACER_ATTR}]`,
  ) as HTMLElement | null;
  return el?.style.width;
}

describe("ChatDockPanelShell chrome inset", () => {
  it("reserves caption-button space on Windows only", () => {
    // Windows caption buttons sit over the dock's toolbar, so the toolbar gets
    // a spacer; macOS traffic lights are on the opposite edge.
    const { container, rerender } = renderShell("right", "windows");
    expect(spacerWidth(container)).toBe(expectedDockSpacer("windows"));

    rerender(
      <DesktopChromeProvider value="mac">
        <ChatDockPanelShell {...baseProps} mode="right" />
      </DesktopChromeProvider>,
    );
    expect(
      container.querySelector(`[${WINDOW_CONTROLS_SPACER_ATTR}]`),
    ).toBeNull();

    rerender(
      <DesktopChromeProvider value="windows">
        <ChatDockPanelShell {...baseProps} mode="popup" />
      </DesktopChromeProvider>,
    );
    expect(spacerWidth(container)).toBe(expectedDockSpacer("windows"));

    rerender(
      <DesktopChromeProvider value="windows">
        <ChatDockPanelShell {...baseProps} mode="bottom" />
      </DesktopChromeProvider>,
    );
    expect(
      container.querySelector(`[${WINDOW_CONTROLS_SPACER_ATTR}]`),
    ).toBeNull();
  });

  it("does not reserve window-control space outside the desktop shell", () => {
    const { container } = renderShell("right", null);
    expect(
      container.querySelector(`[${WINDOW_CONTROLS_SPACER_ATTR}]`),
    ).toBeNull();
  });

  it("disables popup mask while an overlay menu is open", () => {
    const onClose = vi.fn();
    const { container } = render(
      <DesktopChromeProvider value={null}>
        <ChatDockPanelShell
          {...baseProps}
          mode="popup"
          onClose={onClose}
          overlayMenuOpen
        />
      </DesktopChromeProvider>,
    );
    const mask = container.querySelector("[aria-hidden]") as HTMLElement;
    expect(mask.style.pointerEvents).toBe("none");
    mask.click();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("still inserts the spacer from the preload bridge when chrome context is missing", () => {
    // Without a provider the panel falls back to the platform UA; pin it to
    // Windows so the expectation does not depend on the jsdom default.
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    );
    Object.defineProperty(window, "octopDesktop", {
      configurable: true,
      value: {},
    });
    const { container } = render(
      <ChatDockPanelShell {...baseProps} mode="right" />,
    );
    expect(spacerWidth(container)).toBe(
      `${
        windowControlsInset(resolveDesktopChromeStyle(), "end") -
        DOCK_WINDOW_CONTROLS_PAD_PX
      }px`,
    );
    delete (window as Window & { octopDesktop?: unknown }).octopDesktop;
    vi.restoreAllMocks();
  });
});
