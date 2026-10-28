import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyDesktopChrome,
  CHROME_END_PAD_ATTR,
  chromeEndPadValue,
  chromeStartPadValue,
  chromeTopBandPx,
  DESKTOP_CHROME_HEIGHT,
  DESKTOP_DRAG_REGION_CLASS,
  DOCK_WINDOW_CONTROLS_PAD_PX,
  resolveDesktopChromeStyle,
  titleRowEndPadding,
  titleRowStartPadding,
  WINDOW_CONTROLS_INSET,
  WINDOW_CONTROLS_SPACER_ATTR,
  windowControlsEndSpacerPx,
  windowControlsInset,
  windowControlsSide,
  windowControlsStartSpacerPx,
} from "./desktopChrome";
import { isDesktopShell } from "./desktopBridge";

type BridgeHost = Window & { octopDesktop?: unknown };

function stubBridge(): void {
  Object.defineProperty(window, "octopDesktop", {
    configurable: true,
    value: {},
  });
}

describe("desktopChrome", () => {
  afterEach(() => {
    applyDesktopChrome(null);
    delete (window as BridgeHost).octopDesktop;
    vi.unstubAllGlobals();
  });

  it("is inactive without the Electron preload bridge", () => {
    expect(isDesktopShell()).toBe(false);
  });

  it("is active once the preload bridge is exposed", () => {
    stubBridge();
    expect(isDesktopShell()).toBe(true);
  });

  it("uses traffic-light chrome on macOS user agents", () => {
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
      ),
    ).toBe("mac");
  });

  it("uses caption-button chrome on Windows", () => {
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
      ),
    ).toBe("windows");
  });

  it("reserves nothing on Linux, which keeps its native window frame", () => {
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
      ),
    ).toBeNull();
  });

  it("puts the window buttons on the conventional edge per platform", () => {
    // macOS traffic lights → leading (left) edge.
    expect(windowControlsSide("mac")).toBe("start");
    // Windows caption buttons → trailing (right) edge.
    expect(windowControlsSide("windows")).toBe("end");

    expect(windowControlsInset("mac", "start")).toBe(WINDOW_CONTROLS_INSET.mac);
    expect(windowControlsInset("mac", "end")).toBe(0);
    expect(windowControlsInset("windows", "end")).toBe(
      WINDOW_CONTROLS_INSET.windows,
    );
    expect(windowControlsInset("windows", "start")).toBe(0);
    expect(windowControlsInset(null, "end")).toBe(0);
  });

  it("reserves the inset only on the edge that carries buttons", () => {
    expect(WINDOW_CONTROLS_INSET.mac).toBeGreaterThan(0);
    expect(WINDOW_CONTROLS_INSET.windows).toBeGreaterThan(
      WINDOW_CONTROLS_INSET.mac,
    );
    expect(titleRowEndPadding(32)).toContain("--window-controls-inset-end");
    expect(titleRowEndPadding(32)).toContain("32px");
    expect(titleRowStartPadding(32)).toContain("--window-controls-inset-start");
    expect(CHROME_END_PAD_ATTR).toBe("data-octop-chrome-end-pad");
    expect(WINDOW_CONTROLS_SPACER_ATTR).toBe(
      "data-octop-window-controls-spacer",
    );
    expect(chromeEndPadValue(12)).toContain("--window-controls-inset-end");
    expect(chromeEndPadValue(12)).toContain("12px");
    expect(chromeStartPadValue(12)).toContain("--window-controls-inset-start");
    expect(chromeStartPadValue(12)).toContain("12px");

    // Windows keeps the trailing caption buttons clear.
    expect(windowControlsEndSpacerPx("windows", true)).toBe(
      WINDOW_CONTROLS_INSET.windows,
    );
    expect(windowControlsEndSpacerPx("windows", true, 12)).toBe(
      WINDOW_CONTROLS_INSET.windows - 12,
    );
    // macOS buttons moved to the left, so nothing is reserved on the right.
    expect(windowControlsEndSpacerPx("mac", true)).toBe(0);
    expect(windowControlsEndSpacerPx("mac", false)).toBe(0);
    expect(windowControlsEndSpacerPx(null, true)).toBe(0);

    expect(windowControlsStartSpacerPx("mac", true)).toBe(
      WINDOW_CONTROLS_INSET.mac,
    );
    expect(
      windowControlsStartSpacerPx("mac", true, DOCK_WINDOW_CONTROLS_PAD_PX),
    ).toBe(WINDOW_CONTROLS_INSET.mac - DOCK_WINDOW_CONTROLS_PAD_PX);
    expect(windowControlsStartSpacerPx("windows", true)).toBe(0);
    expect(windowControlsStartSpacerPx("mac", false)).toBe(0);
    expect(windowControlsStartSpacerPx(null, true)).toBe(0);
  });

  it("reserves a top band for the macOS traffic lights only", () => {
    expect(chromeTopBandPx("mac")).toBe(DESKTOP_CHROME_HEIGHT);
    expect(chromeTopBandPx("windows")).toBe(0);
    expect(chromeTopBandPx(null)).toBe(0);
    // Full screen hides the traffic lights, so nothing is reserved there either.
    expect(chromeTopBandPx("mac", true)).toBe(0);
    // A band smaller than the buttons would let them cover the brand row.
    expect(DESKTOP_CHROME_HEIGHT).toBeGreaterThanOrEqual(32);
  });

  it("pads right-edge overlays away from the native caption buttons", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    expect(css).toContain("[data-octop-chrome-end-pad]");
    expect(css).not.toContain("[data-dock-panel]");
    expect(css).toContain(".octop-drawer-right");
    expect(css).toMatch(/padding-inline-end:\s*max\(/);
  });

  it("drags shell windows through the app-region CSS property", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    expect(css).toContain(".octop-desktop-drag");
    expect(css).toContain("-webkit-app-region: drag");
    expect(css).toContain("-webkit-app-region: no-drag");
    expect(css).not.toContain("wails");
    expect(DESKTOP_DRAG_REGION_CLASS).toBe("octop-desktop-drag");
  });

  it("writes both inset tokens on <html> and can clear them", () => {
    applyDesktopChrome("mac");
    expect(document.documentElement.dataset.octopDesktopChrome).toBe("mac");
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-start",
      ),
    ).toBe(`${WINDOW_CONTROLS_INSET.mac}px`);
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-end",
      ),
    ).toBe("0px");

    applyDesktopChrome("windows");
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-start",
      ),
    ).toBe("0px");
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-end",
      ),
    ).toBe(`${WINDOW_CONTROLS_INSET.windows}px`);

    applyDesktopChrome(null);
    expect(document.documentElement.dataset.octopDesktopChrome).toBeUndefined();
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-start",
      ),
    ).toBe("");
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-end",
      ),
    ).toBe("");
  });
});
