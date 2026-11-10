import { nativeTheme } from "electron";
import type { BrowserWindow, BrowserWindowConstructorOptions } from "electron";

/**
 * Native window chrome. The shell does not draw caption buttons.
 *
 * - macOS   `titleBarStyle: "hidden"` keeps the traffic lights and pins them
 *           over the Dashboard's chrome row; the titlebar itself is gone.
 * - Windows hides the opaque caption and overlays the native buttons on a
 *           transparent strip, so the page shows through. The menu and the
 *           window buttons share that one row: the native menu bar stays
 *           hidden, and the dashboard draws File / Edit / View / Help once
 *           it mounts. The menu stays installed so its accelerators still fire.
 * - Linux uses the same hidden title bar and the same menu row, but does not
 *           enable the overlay. That overlay paints Adwaita circles. The page
 *           draws square caption buttons instead, and the close button turns
 *           red on hover.
 */

/** Caption buttons sit on the page. macOS uses traffic lights instead. */
export function usesCaptionOverlay(
  platform: NodeJS.Platform = process.platform,
): boolean {
  return platform === "win32" || platform === "linux";
}

/**
 * 与 Dashboard 的 DESKTOP_CHROME_HEIGHT 及早期页顶部拖动区域保持一致。
 * 这是页面顶栏，不是交通灯的高度。
 */
export const CHROME_ROW_HEIGHT = 58;

/** Windows caption overlay. Matches the Dashboard's `WINDOWS_CAPTION_HEIGHT`. */
export const WINDOWS_TITLE_BAR_HEIGHT = 32;

/** Fully transparent so the page background is the title bar. */
export const WINDOWS_TITLE_BAR_COLOR = "#00000000";

/**
 * 系统交通灯就是 12×12，间距 8，整组宽 52。标题栏高 28，灯在里面垂直居中。
 * 不把灯拉高到页面顶栏的 58px。
 */
export const TRAFFIC_LIGHT_BUTTON = 12;
export const TRAFFIC_LIGHT_GAP = 8;
const TRAFFIC_LIGHT_SPAN = TRAFFIC_LIGHT_BUTTON * 3 + TRAFFIC_LIGHT_GAP * 2;
export const TRAFFIC_LIGHT_ROW_HEIGHT = 28;
const TRAFFIC_LIGHT_INSET = 12;
const TRAFFIC_LIGHT_TOP = (TRAFFIC_LIGHT_ROW_HEIGHT - TRAFFIC_LIGHT_BUTTON) / 2;

export const TRAFFIC_LIGHT_POSITION = {
  x: TRAFFIC_LIGHT_INSET,
  y: TRAFFIC_LIGHT_TOP,
} as const;

/** Theme the renderer reports; ``scheme`` keeps "follow the system" live. */
export interface WindowChromeTheme {
  mode: "light" | "dark";
  scheme?: "system" | "light" | "dark";
}

/** What the OS is showing right now, used before the renderer reports a theme. */
export function systemMode(): WindowChromeTheme["mode"] {
  return nativeTheme.shouldUseDarkColors ? "dark" : "light";
}

/** Resolve the persisted preference into the pair the chrome needs. */
export function resolveWindowChromeTheme(
  scheme: "system" | "light" | "dark",
): WindowChromeTheme {
  return { mode: scheme === "system" ? systemMode() : scheme, scheme };
}

/**
 * Window colour before the page paints. Same as the Dashboard page ground
 * (`--fn-bg-layout` in theme-vars.css) so the shell and the app do not shift.
 */
const WINDOW_BACKGROUND = {
  light: "#f5f6f8",
  dark: "#0e0e0e",
} as const;

export function windowBackground(mode: WindowChromeTheme["mode"]): string {
  return WINDOW_BACKGROUND[mode];
}

/**
 * Query key read by the Dashboard boot script (`dashboard/index.html`).
 * The value is the preference (`system` | `light` | `dark`), not the resolved mode.
 */
export const DASHBOARD_THEME_QUERY = "octopTheme";

/** Packaged pages live on the privileged scheme. Local dev uses the Vite origin. */
export const PACKAGED_APP_ORIGIN = "octop://app";

export function dashboardEntryUrl(
  scheme: "system" | "light" | "dark",
  appOrigin: string = PACKAGED_APP_ORIGIN,
): string {
  return `${appOrigin}/?${DASHBOARD_THEME_QUERY}=${scheme}`;
}

/** In-app navigations, including a Vite full reload on the dev origin. */
export function isAppNavigation(url: string, appOrigin: string): boolean {
  return url === appOrigin || url.startsWith(`${appOrigin}/`) || url.startsWith(`${appOrigin}?`);
}

/** Caption overlay. `color` stays clear; only the button glyphs follow the theme. */
export function windowsTitleBarOverlay(mode: WindowChromeTheme["mode"]): {
  color: string;
  symbolColor: string;
  height: number;
} {
  return {
    color: WINDOWS_TITLE_BAR_COLOR,
    symbolColor: mode === "dark" ? "#ffffff" : "#1a1a1a",
    height: WINDOWS_TITLE_BAR_HEIGHT,
  };
}

/** Per-platform frame options, shared by the Early Window and the Dashboard. */
export function windowChrome(
  mode: WindowChromeTheme["mode"] = systemMode(),
): BrowserWindowConstructorOptions {
  if (process.platform === "darwin") {
    return {
      titleBarStyle: "hidden",
      trafficLightPosition: { ...TRAFFIC_LIGHT_POSITION },
    };
  }
  if (usesCaptionOverlay()) {
    return {
      titleBarStyle: "hidden",
      // Hidden from the first frame. The splash and the dashboard boot screen
      // have no page menu; showing the native bar there is a second row above
      // the caption buttons. The dashboard draws the menu into that same row
      // after it mounts.
      autoHideMenuBar: true,
      // Linux omits the overlay. Electron's Linux overlay buttons are round;
      // the page draws square ones and talks to the window over IPC.
      ...(process.platform === "linux"
        ? {}
        : { titleBarOverlay: windowsTitleBarOverlay(mode) }),
    };
  }
  return {};
}

let windowsCaptionMode: WindowChromeTheme["mode"] = systemMode();

/** Fullscreen hides the caption buttons. Leaving it puts the last theme back. */
export function windowsCaptionOverlay(visible: boolean): {
  color: string;
  symbolColor: string;
  height: number;
} {
  if (!visible) {
    return {
      color: WINDOWS_TITLE_BAR_COLOR,
      symbolColor: WINDOWS_TITLE_BAR_COLOR,
      height: 0,
    };
  }
  return windowsTitleBarOverlay(windowsCaptionMode);
}

/**
 * Keep the native menu bar off this window. `autoHideMenuBar` alone still
 * paints the bar on the first show when an application menu was installed
 * before the window existed — which is exactly the splash.
 */
export function concealWindowsMenuBar(win: BrowserWindow): void {
  if (!usesCaptionOverlay() || win.isDestroyed()) return;
  win.setAutoHideMenuBar(true);
  win.setMenuBarVisibility(false);
}

export function setWindowsCaptionVisible(win: BrowserWindow, visible: boolean): void {
  // Linux has no overlay to hide. `setTitleBarOverlay` throws unless one was
  // enabled at construction. The page hides its own buttons on fullscreen.
  if (process.platform === "linux" || !usesCaptionOverlay() || win.isDestroyed()) return;
  win.setTitleBarOverlay(windowsCaptionOverlay(visible));
}

/**
 * Apply a renderer-reported theme to the window's *native* controls. They follow
 * `nativeTheme`, not the page's CSS variables, so a dark Dashboard would
 * otherwise keep black glyphs on a dark overlay. A fullscreen window keeps its
 * buttons hidden until it leaves fullscreen.
 */
export function applyWindowChromeTheme(
  win: BrowserWindow,
  theme: WindowChromeTheme,
): void {
  applyNativeTheme(theme);
  windowsCaptionMode = theme.mode;
  if (
    process.platform === "linux" ||
    !usesCaptionOverlay() ||
    win.isDestroyed() ||
    win.isFullScreen()
  ) {
    return;
  }
  win.setTitleBarOverlay(windowsTitleBarOverlay(theme.mode));
}

/**
 * Make the OS draw its own chrome (traffic lights, menus, dialogs) in the app's
 * theme. `scheme` (not `mode`) so "system" keeps tracking the OS preference
 * instead of pinning today's answer.
 */
export function applyNativeTheme(theme: WindowChromeTheme): void {
  nativeTheme.themeSource = theme.scheme ?? theme.mode;
}

/** Validate an IPC payload; anything malformed is dropped rather than applied. */
export function parseWindowChromeTheme(
  value: unknown,
): WindowChromeTheme | null {
  if (typeof value !== "object" || value === null) return null;
  const { mode, scheme } = value as Record<string, unknown>;
  if (mode !== "light" && mode !== "dark") return null;
  if (
    scheme !== undefined &&
    scheme !== "system" &&
    scheme !== "light" &&
    scheme !== "dark"
  ) {
    return null;
  }
  return scheme === undefined ? { mode } : { mode, scheme };
}
