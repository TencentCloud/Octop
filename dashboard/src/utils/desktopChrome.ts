import { getDesktopBridge } from "./desktopBridge";

export type DesktopChromeStyle = "mac" | "windows";
export type DesktopWindowAction = "minimise" | "toggle-maximise" | "close";

/** Which window edge carries the minimise / maximise / close buttons. */
export type WindowControlsSide = "start" | "end";

/**
 * Height of the shell's own chrome row. The buttons are 32px tall, so anything
 * that wants to start *below* them (macOS sidebar) reserves this band.
 */
export const DESKTOP_CHROME_HEIGHT = 32;

/**
 * Horizontal space the buttons occupy, by platform convention:
 * - macOS: three 12px traffic lights on the LEFT + gaps + padding.
 * - Windows: three 46px caption buttons on the RIGHT.
 */
export const WINDOW_CONTROLS_INSET: Record<DesktopChromeStyle, number> = {
  mac: 80,
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
 * Vertical band to reserve at the top of a full-height column (the sidebar on
 * macOS, where the traffic lights float above it). Windows caption buttons sit
 * over the content column instead, so they need no band.
 */
export function chromeTopBandPx(style: DesktopChromeStyle | null): number {
  return style === "mac" ? DESKTOP_CHROME_HEIGHT : 0;
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
 * Marks shell chrome the frameless Electron window treats as a drag region.
 * `layout.css` maps these classes to `-webkit-app-region: drag` / `no-drag`
 * once `data-octop-desktop-chrome` is on `<html>`.
 */
export const DESKTOP_DRAG_REGION_CLASS = "octop-desktop-drag";
export const DESKTOP_NO_DRAG_CLASS = "octop-desktop-no-drag";

export function resolveDesktopChromeStyle(
  userAgent = navigator.userAgent,
): DesktopChromeStyle {
  if (/Mac|iPhone|iPad/.test(userAgent)) return "mac";
  return "windows";
}

export function titleRowEndPadding(outerPadPx: number): string {
  return `max(0px, calc(var(${INSET_END_VAR}, 0px) - ${outerPadPx}px))`;
}

/** Start-edge counterpart of {@link titleRowEndPadding}. */
export function titleRowStartPadding(outerPadPx: number): string {
  return `max(0px, calc(var(${INSET_START_VAR}, 0px) - ${outerPadPx}px))`;
}

export function applyDesktopChrome(
  style: DesktopChromeStyle | null,
  root: HTMLElement = document.documentElement,
): void {
  if (!style) {
    delete root.dataset.octopDesktopChrome;
    root.style.removeProperty(INSET_START_VAR);
    root.style.removeProperty(INSET_END_VAR);
    return;
  }
  root.dataset.octopDesktopChrome = style;
  // Only one edge carries buttons per platform; the other stays at 0 so every
  // consumer can use both variables unconditionally.
  root.style.setProperty(
    INSET_START_VAR,
    `${windowControlsInset(style, "start")}px`,
  );
  root.style.setProperty(
    INSET_END_VAR,
    `${windowControlsInset(style, "end")}px`,
  );
}

const WINDOW_CONTROL_ACTION: Record<
  DesktopWindowAction,
  "minimize" | "maximize" | "close"
> = {
  minimise: "minimize",
  "toggle-maximise": "maximize",
  close: "close",
};

/**
 * Ask the shell to minimise / maximise / close the window. Returns false in the
 * browser (server mode), where there is no window to drive.
 */
export function emitDesktopWindowAction(action: DesktopWindowAction): boolean {
  const bridge = getDesktopBridge();
  if (!bridge) return false;
  bridge.windowControls(WINDOW_CONTROL_ACTION[action]);
  return true;
}
