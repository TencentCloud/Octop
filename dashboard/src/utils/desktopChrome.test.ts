import { afterEach, describe, expect, it, vi } from "vitest";
import {
  applyDesktopChrome,
  emitDesktopWindowAction,
  installDesktopWindowDrag,
  isDesktopShell,
  resolveDesktopChromeStyle,
  shouldArmDesktopDrag,
  titleRowEndPadding,
  WINDOW_CONTROLS_INSET,
  DESKTOP_DRAG_REGION_CLASS,
} from "./desktopChrome";

describe("desktopChrome", () => {
  afterEach(() => {
    applyDesktopChrome(null);
    delete document.documentElement.dataset.octopDragReady;
    vi.unstubAllGlobals();
  });

  it("is inactive when the Wails bridge is missing", () => {
    expect(isDesktopShell({} as Window)).toBe(false);
  });

  it("is active when Wails invoke is present", () => {
    expect(
      isDesktopShell({ _wails: { invoke: () => undefined } } as Window),
    ).toBe(true);
  });

  it("uses traffic-light chrome on macOS user agents", () => {
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
      ),
    ).toBe("mac");
  });

  it("uses caption-button chrome on Windows and Linux", () => {
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
      ),
    ).toBe("windows");
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
      ),
    ).toBe("windows");
  });

  it("reserves a trailing inset only for the title row", () => {
    expect(WINDOW_CONTROLS_INSET.mac).toBeGreaterThan(0);
    expect(WINDOW_CONTROLS_INSET.windows).toBeGreaterThan(
      WINDOW_CONTROLS_INSET.mac,
    );
    expect(titleRowEndPadding(32)).toContain("--window-controls-inset-end");
    expect(titleRowEndPadding(32)).toContain("32px");
  });

  it("exports a stable class for Wails title-bar dragging", () => {
    expect(DESKTOP_DRAG_REGION_CLASS).toBe("octop-desktop-drag");
  });

  it("writes the inset token on <html> and can clear it", () => {
    applyDesktopChrome("mac");
    expect(document.documentElement.dataset.octopDesktopChrome).toBe("mac");
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-end",
      ),
    ).toBe(`${WINDOW_CONTROLS_INSET.mac}px`);

    applyDesktopChrome(null);
    expect(document.documentElement.dataset.octopDesktopChrome).toBeUndefined();
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-end",
      ),
    ).toBe("");
  });

  it("emits Wails window actions through the existing event bridge", () => {
    const invoke = vi.fn();
    const emitted = emitDesktopWindowAction("minimise", {
      _wails: { invoke },
    } as Window);
    expect(emitted).toBe(true);
    expect(invoke).toHaveBeenCalledWith("wails:event:emit:desktop:minimise");
  });

  it("arms drag on --wails-draggable regions and the top chrome strip", () => {
    const region = document.createElement("div");
    region.style.setProperty("--wails-draggable", "drag");
    document.body.appendChild(region);
    const button = document.createElement("button");
    region.appendChild(button);
    const chrome = document.createElement("div");
    document.body.appendChild(chrome);

    expect(shouldArmDesktopDrag(mouseOn(region, 80))).toBe(true);
    expect(shouldArmDesktopDrag(mouseOn(button, 10))).toBe(false);
    expect(shouldArmDesktopDrag(mouseOn(chrome, 10))).toBe(true);
    expect(shouldArmDesktopDrag(mouseOn(chrome, 80))).toBe(false);

    region.remove();
    chrome.remove();
  });

  it("starts a Wails window drag after a move on an armed title-bar target", () => {
    const invoke = vi.fn();
    Object.defineProperty(window, "_wails", {
      configurable: true,
      value: { invoke },
    });
    expect(installDesktopWindowDrag()).toBe(true);
    expect(installDesktopWindowDrag()).toBe(false);

    const region = document.createElement("div");
    region.style.setProperty("--wails-draggable", "drag");
    document.body.appendChild(region);
    region.dispatchEvent(
      new MouseEvent("mousedown", {
        button: 0,
        clientY: 80,
        screenX: 40,
        screenY: 40,
        bubbles: true,
      }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", {
        button: 0,
        screenX: 52,
        screenY: 48,
        bubbles: true,
      }),
    );
    expect(invoke).toHaveBeenCalledWith("wails:drag");

    region.dispatchEvent(
      new MouseEvent("dblclick", {
        button: 0,
        clientY: 80,
        bubbles: true,
      }),
    );
    expect(invoke).toHaveBeenCalledWith("wails:drag:doubleclick");
    region.remove();
    delete document.documentElement.dataset.octopDragReady;
    delete (window as Window & { _wails?: unknown })._wails;
  });
});

function mouseOn(
  target: Element,
  clientY: number,
): Pick<MouseEvent, "button" | "clientY" | "target"> {
  return { button: 0, clientY, target };
}
