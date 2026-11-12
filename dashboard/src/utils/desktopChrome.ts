export type DesktopChromeStyle = "mac" | "windows";

/** Which window edge carries the minimise / maximise / close buttons. */
export type WindowControlsSide = "start" | "end";

/** Shared Web/desktop page-header height. Native traffic lights are shorter. */
export const DESKTOP_CHROME_HEIGHT = 58;

/** Native macOS traffic light: 12×12, 8px apart. The page header is taller. */
export const MAC_TRAFFIC_LIGHT_BUTTON = 12;
export const MAC_TRAFFIC_LIGHT_GAP = 8;

/**
 * Left margin of a standard title bar. Matches `TRAFFIC_LIGHT_POSITION.x`.
 */
export const MAC_TRAFFIC_LIGHT_INSET = 12;

/** 12×3 + 8×2. Not the wider measurement, and not the 58px page row. */
export const MAC_TRAFFIC_LIGHT_SPAN =
  MAC_TRAFFIC_LIGHT_BUTTON * 3 + MAC_TRAFFIC_LIGHT_GAP * 2;

/** Standard title bar. Traffic lights are centered in this, not stretched. */
export const MAC_TITLEBAR_HEIGHT = 28;

/** Windows caption buttons. Same idea: system height, not the page row. */
export const WINDOWS_CAPTION_HEIGHT = 32;

/**
 * Horizontal space the *native* buttons occupy, by platform convention:
 * - macOS: three 12×12 traffic lights on the LEFT, with the standard 12px
 *   margin on both sides of the group. The page header below stays taller.
 * - Windows and Linux: three caption buttons on the RIGHT (titleBarOverlay).
 *   Linux shares this contract so the menu and the buttons occupy one row.
 *
 * The buttons are drawn by the OS above the page, so the page must keep this
 * strip empty — it cannot draw under them.
 */
export const WINDOW_CONTROLS_INSET: Record<DesktopChromeStyle, number> = {
  mac: MAC_TRAFFIC_LIGHT_INSET * 2 + MAC_TRAFFIC_LIGHT_SPAN,
  windows: 138,
};

/**
 * macOS keeps its traffic lights at the leading edge, Windows its caption
 * buttons at the trailing edge. Everything below derives from this one rule.
 */
export function windowControlsSide(
  style: DesktopChromeStyle,
): WindowControlsSide {
  return style === "mac" ? "start" : "end";
}

/** Inset reserved on ONE edge; the opposite edge is always 0 for that platform. */
export function windowControlsInset(
  style: DesktopChromeStyle | null,
  side: WindowControlsSide,
): number {
  if (!style || windowControlsSide(style) !== side) return 0;
  return WINDOW_CONTROLS_INSET[style];
}

/**
 * Height of the native control row. macOS title bar is 28px and Windows
 * caption buttons are 32px. The 58px page header is a separate row.
 * Fullscreen and `null` (browser / system frame with no overlay) reserve none.
 */
export function chromeTopBandPx(
  style: DesktopChromeStyle | null,
  fullscreen = false,
): number {
  if (!style || fullscreen) return 0;
  return style === "mac" ? MAC_TITLEBAR_HEIGHT : WINDOWS_CAPTION_HEIGHT;
}

/** Right-edge overlay chrome (dock toolbar, etc.) to keep clear of caption buttons. */
export const CHROME_END_PAD_ATTR = "data-octop-chrome-end-pad";
export const WINDOW_CONTROLS_SPACER_ATTR = "data-octop-window-controls-spacer";

/**
 * Dock toolbar already has 12px end padding. Subtract that plus 6px so the
 * ⋮ / close group sits a few pixels closer to the caption buttons than the
 * personalization title row.
 */
export const DOCK_WINDOW_CONTROLS_PAD_PX = 18;

const INSET_START_VAR = "--window-controls-inset-start";
const INSET_END_VAR = "--window-controls-inset-end";

/** Inline padding so CSS-module `padding` shorthands cannot clobber the inset. */
export function chromeEndPadValue(minPx = 12): string {
  return `max(${minPx}px, var(${INSET_END_VAR}, 0px))`;
}

/** Start-edge counterpart of {@link chromeEndPadValue} (macOS traffic lights). */
export function chromeStartPadValue(minPx = 12): string {
  return `max(${minPx}px, var(${INSET_START_VAR}, 0px))`;
}

/** Pixel width of a flex spacer that clears overlay caption buttons. */
export function windowControlsEndSpacerPx(
  chrome: DesktopChromeStyle | null,
  panelTouchesWindowEnd: boolean,
  existingEndPadPx = 0,
): number {
  if (!chrome || !panelTouchesWindowEnd) return 0;
  return Math.max(0, windowControlsInset(chrome, "end") - existingEndPadPx);
}

/** Start-edge counterpart, for panels that touch the macOS traffic lights. */
export function windowControlsStartSpacerPx(
  chrome: DesktopChromeStyle | null,
  panelTouchesWindowStart: boolean,
  existingStartPadPx = 0,
): number {
  if (!chrome || !panelTouchesWindowStart) return 0;
  return Math.max(0, windowControlsInset(chrome, "start") - existingStartPadPx);
}

/**
 * Marks shell chrome the shell window treats as a drag region.
 * `layout.css` maps these classes to `-webkit-app-region: drag` / `no-drag`
 * once `data-octop-desktop-chrome` is on `<html>`.
 */
export const DESKTOP_DRAG_REGION_CLASS = "octop-desktop-drag";
export const DESKTOP_NO_DRAG_CLASS = "octop-desktop-no-drag";

/**
 * Which chrome — if any — the page has to make room for.
 *
 * macOS traffic lights and the Windows/Linux caption overlay both sit on the
 * page, so the page reserves their strip. `"windows"` is that shared overlay
 * (buttons on the trailing edge, menu in the same row), including UOS and
 * other desktop Linux. Android keeps the browser frame.
 */
export function resolveDesktopChromeStyle(
  userAgent = navigator.userAgent,
): DesktopChromeStyle | null {
  if (/Mac|iPhone|iPad/.test(userAgent)) return "mac";
  if (/Windows/.test(userAgent)) return "windows";
  if (/Linux/.test(userAgent) && !/Android/.test(userAgent)) return "windows";
  return null;
}

export function titleRowEndPadding(outerPadPx: number): string {
  return `max(0px, calc(var(${INSET_END_VAR}, 0px) - ${outerPadPx}px))`;
}

/** Start-edge counterpart of {@link titleRowEndPadding}. */
export function titleRowStartPadding(outerPadPx: number): string {
  return `max(0px, calc(var(${INSET_START_VAR}, 0px) - ${outerPadPx}px))`;
}

/**
 * Publish the platform's chrome contract on `<html>`: one attribute for the CSS
 * hooks (drag regions) and the two inset tokens every consumer reads.
 * `null` means "no chrome to reserve" — the browser, or Android.
 */
export function applyDesktopChrome(
  style: DesktopChromeStyle | null,
  root: HTMLElement = document.documentElement,
  fullscreen = false,
): void {
  if (!style) {
    delete root.dataset.octopDesktopChrome;
    root.style.removeProperty(INSET_START_VAR);
    root.style.removeProperty(INSET_END_VAR);
    return;
  }
  root.dataset.octopDesktopChrome = style;
  // Fullscreen hides the native buttons, so neither edge keeps a gap.
  // Only one edge carries buttons per platform; the other stays at 0 so every
  // consumer can use both variables unconditionally.
  root.style.setProperty(
    INSET_START_VAR,
    `${fullscreen ? 0 : windowControlsInset(style, "start")}px`,
  );
  root.style.setProperty(
    INSET_END_VAR,
    `${fullscreen ? 0 : windowControlsInset(style, "end")}px`,
  );
}
