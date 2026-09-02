import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DesktopChromeProvider } from "../../hooks/useDesktopChrome";
import {
  DOCK_WINDOW_CONTROLS_PAD_PX,
  WINDOW_CONTROLS_INSET,
  WINDOW_CONTROLS_SPACER_ATTR,
  resolveDesktopChromeStyle,
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
  return `${WINDOW_CONTROLS_INSET[chrome] - DOCK_WINDOW_CONTROLS_PAD_PX}px`;
}

function spacerWidth(container: HTMLElement): string | undefined {
  const el = container.querySelector(
    `[${WINDOW_CONTROLS_SPACER_ATTR}]`,
  ) as HTMLElement | null;
  return el?.style.width;
}

describe("ChatDockPanelShell chrome inset", () => {
  it("inserts a pixel spacer so right-dock and popup toolbars clear window controls", () => {
    const { container, rerender } = renderShell("right", "mac");
    expect(spacerWidth(container)).toBe(expectedDockSpacer("mac"));

    rerender(
      <DesktopChromeProvider value="windows">
        <ChatDockPanelShell {...baseProps} mode="popup" />
      </DesktopChromeProvider>,
    );
    expect(spacerWidth(container)).toBe(expectedDockSpacer("windows"));

    rerender(
      <DesktopChromeProvider value="mac">
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

  it("still inserts the spacer from the Wails bridge when chrome context is missing", () => {
    Object.defineProperty(window, "_wails", {
      configurable: true,
      value: { invoke: () => undefined },
    });
    const { container } = render(
      <ChatDockPanelShell {...baseProps} mode="right" />,
    );
    expect(spacerWidth(container)).toBe(
      `${
        WINDOW_CONTROLS_INSET[resolveDesktopChromeStyle()] -
        DOCK_WINDOW_CONTROLS_PAD_PX
      }px`,
    );
    delete (window as Window & { _wails?: unknown })._wails;
  });
});
