import { nativeTheme } from "electron";
import type { BrowserWindow, BrowserWindowConstructorOptions } from "electron";

/**
 * Native window chrome, after opencode's desktop shell: the shell keeps the
 * platform's own buttons and only reserves the space for them, instead of
 * drawing a fake titlebar. Every window-level gesture (drag, double-click to
 * zoom, Aero Snap, Snap Layouts, full-screen transitions) therefore stays in
 * the hands of the OS.
 *
 * - macOS   `titleBarStyle: "hidden"` keeps the traffic lights and pins them
 *           over the Dashboard's chrome row; the titlebar itself is gone.
 * - Windows `titleBarOverlay` draws the three caption buttons *above* the page.
 *           The overlay colour is fully transparent so the page background
 *           shows through, and only the glyph colour has to follow the theme.
 * - Linux   keeps the system frame, so no option is passed at all: a frameless
 *           window there would have no controls whatsoever.
 */

/**
 * 与 Dashboard 的 DESKTOP_CHROME_HEIGHT 及早期页顶部拖动区域保持一致；
 * Windows 原生标题栏按钮覆盖此高度。
 */
export const CHROME_ROW_HEIGHT = 58;

/**
 * 交通灯距窗口左缘和上缘的距离相同。
 * 顶栏高 58px，按钮约 12px，垂直居中放在 (58-12)/2 = 23，左边距取同一个值。
 */
export const TRAFFIC_LIGHT_POSITION = {
  x: 23,
  y: 23,
} as const;

/** Theme the renderer reports; ``scheme`` keeps "follow the system" live. */
export interface WindowChromeTheme {
  mode: "light" | "dark";
  scheme?: "system" | "light" | "dark";
}

const DARK_SYMBOL = "#e7e7ed";
const LIGHT_SYMBOL = "#1f2329";

interface TitlebarOverlay {
  color: string;
  symbolColor: string;
  height: number;
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

/**
 * Caption-button overlay. `color` stays transparent on purpose: the page paints
 * its own background underneath, so a themed bar would leave a visible seam.
 */
export function titlebarOverlay(
  mode: WindowChromeTheme["mode"] = systemMode(),
): TitlebarOverlay {
  return {
    color: "#00000000",
    symbolColor: mode === "dark" ? DARK_SYMBOL : LIGHT_SYMBOL,
    height: CHROME_ROW_HEIGHT,
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
  if (process.platform === "win32") {
    return {
      frame: false,
      titleBarStyle: "hidden",
      titleBarOverlay: titlebarOverlay(mode),
    };
  }
  return {};
}

/**
 * Apply a renderer-reported theme to the window's *native* controls. They follow
 * `nativeTheme`, not the page's CSS variables, so a dark Dashboard would
 * otherwise keep black glyphs on a dark overlay.
 */
export function applyWindowChromeTheme(
  win: BrowserWindow,
  theme: WindowChromeTheme,
): void {
  applyNativeTheme(theme);
  if (win.isDestroyed() || process.platform !== "win32") return;
  win.setTitleBarOverlay(titlebarOverlay(theme.mode));
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
