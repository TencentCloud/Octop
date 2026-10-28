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
 * Height of the Dashboard's own chrome row (`DESKTOP_CHROME_HEIGHT` in
 * `dashboard/src/utils/desktopChrome.ts`). Both the traffic lights and the
 * Windows caption buttons have to line up with it.
 */
export const CHROME_ROW_HEIGHT = 32;

/**
 * Native traffic lights: 14px in from the leading edge (the Dashboard reserves
 * 80px there) and vertically centred in the 32px row.
 */
export const TRAFFIC_LIGHT_POSITION = {
  x: 14,
  y: Math.round((CHROME_ROW_HEIGHT - 12) / 2),
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
