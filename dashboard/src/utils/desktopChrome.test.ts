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
  MAC_TITLEBAR_HEIGHT,
  MAC_TRAFFIC_LIGHT_BUTTON,
  MAC_TRAFFIC_LIGHT_GAP,
  MAC_TRAFFIC_LIGHT_INSET,
  MAC_TRAFFIC_LIGHT_SPAN,
  WINDOWS_CAPTION_HEIGHT,
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

  it("reserves the caption overlay on Windows and desktop Linux", () => {
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
      ),
    ).toBe("windows");
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138.0.0.0",
      ),
    ).toBe("windows");
    expect(
      resolveDesktopChromeStyle(
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
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

  it("reserves the conventional control height, not the taller page header", () => {
    expect(MAC_TITLEBAR_HEIGHT).toBe(28);
    expect(WINDOWS_CAPTION_HEIGHT).toBe(32);
    expect(MAC_TITLEBAR_HEIGHT).toBeLessThan(DESKTOP_CHROME_HEIGHT);
    expect(chromeTopBandPx("mac")).toBe(MAC_TITLEBAR_HEIGHT);
    expect(chromeTopBandPx("windows")).toBe(WINDOWS_CAPTION_HEIGHT);
    expect(chromeTopBandPx(null)).toBe(0);
    expect(chromeTopBandPx("mac", true)).toBe(0);
    expect(chromeTopBandPx("windows", true)).toBe(0);
    expect(DESKTOP_CHROME_HEIGHT).toBe(58);
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

  it("drags macOS windows from the drawer header only", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    expect(css).toMatch(
      /html\[data-octop-desktop-chrome="mac"\] \.octop-drawer-header,[\s\S]*?-webkit-app-region:\s*drag/,
    );
    expect(css).toMatch(
      /html\[data-octop-desktop-chrome="mac"\] \.ant-drawer-header[\s\S]*?-webkit-app-region:\s*drag/,
    );
    expect(css).not.toMatch(
      /html\[data-octop-desktop-chrome="windows"\][^{]*drawer-header/,
    );
  });

  it("lays the Windows caption above the popup stage", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    expect(css).toMatch(
      /html\[data-octop-caption-row\] body\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column/,
    );
    expect(css).toMatch(
      /html\[data-octop-caption-row\] #octop-stage\s*\{[^}]*flex:\s*1 1 auto;[^}]*transform:\s*translateY\(0\)/,
    );
    expect(css).toMatch(
      /html\[data-octop-caption-row\] #root\s*\{[^}]*min-height:\s*0/,
    );
    expect(css).not.toMatch(/\.octop-win-menu\s*\{[^}]*z-index/);
    expect(css).not.toMatch(/\.octop-win-menu\s*\{[^}]*position:\s*fixed/);
    expect(css).not.toMatch(
      /html\[data-octop-caption-row\] \.octop-drawer\s*\{[^}]*--octop-caption-row/,
    );
  });

  it("drags shell windows through the app-region CSS property", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    expect(css).toContain(".octop-desktop-drag");
    expect(css).toContain("-webkit-app-region: drag");
    expect(css).toContain("-webkit-app-region: no-drag");
    expect(DESKTOP_DRAG_REGION_CLASS).toBe("octop-desktop-drag");
  });

  it("keeps controls and portalled overlays out of the drag band", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/layout.css"),
      "utf8",
    );
    for (const selector of [
      "button",
      "a",
      "input",
      "textarea",
      "select",
      "label",
      '[role="button"]',
      '[role="tab"]',
      '[role="separator"]',
      '[role="combobox"]',
      '[role="menu"]',
      '[role="dialog"]',
      '[role="alertdialog"]',
      "[tabindex]",
      '[contenteditable]:not([contenteditable="false"])',
      "[data-octop-no-drag]",
    ]) {
      expect(css).toContain(`html[data-octop-desktop-chrome] ${selector}`);
    }
  });

  it("shares the top row height across Web, native chrome and chat themes", () => {
    const theme = readFileSync(
      resolve(__dirname, "../styles/theme-vars.css"),
      "utf8",
    );
    const native = readFileSync(
      resolve(__dirname, "../../../desktop/src/main/windows/chrome.ts"),
      "utf8",
    );
    expect(native).toContain(`CHROME_ROW_HEIGHT = ${DESKTOP_CHROME_HEIGHT}`);
    expect(native).toContain(
      `TRAFFIC_LIGHT_BUTTON = ${MAC_TRAFFIC_LIGHT_BUTTON}`,
    );
    expect(native).toContain(
      `TRAFFIC_LIGHT_ROW_HEIGHT = ${MAC_TITLEBAR_HEIGHT}`,
    );
    expect(native).toContain(`TRAFFIC_LIGHT_GAP = ${MAC_TRAFFIC_LIGHT_GAP}`);
    expect(MAC_TRAFFIC_LIGHT_BUTTON).toBe(12);
    expect(MAC_TRAFFIC_LIGHT_GAP).toBe(8);
    expect(MAC_TRAFFIC_LIGHT_SPAN).toBe(52);
    expect(MAC_TRAFFIC_LIGHT_INSET).toBe(12);
    expect(WINDOW_CONTROLS_INSET.mac).toBe(
      MAC_TRAFFIC_LIGHT_INSET * 2 + MAC_TRAFFIC_LIGHT_SPAN,
    );
    const heights = [...theme.matchAll(/--fn-chat-chrome-height:\s*(\d+)px/g)];
    expect(heights.length).toBeGreaterThan(0);
    for (const [, height] of heights)
      expect(Number(height)).toBe(DESKTOP_CHROME_HEIGHT);
  });

  it("does not turn navigation or page bodies into extra drag regions", () => {
    for (const file of [
      "../layouts/Sidebar.tsx",
      "../layouts/PageShell.tsx",
      "../pages/Chat/components/ChatTitleBar.tsx",
    ]) {
      const source = readFileSync(resolve(__dirname, file), "utf8");
      expect(source).not.toContain("DESKTOP_DRAG_REGION_CLASS");
    }
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

    applyDesktopChrome("windows", document.documentElement, true);
    expect(document.documentElement.dataset.octopDesktopChrome).toBe("windows");
    expect(
      document.documentElement.style.getPropertyValue(
        "--window-controls-inset-end",
      ),
    ).toBe("0px");

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
