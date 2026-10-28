export type DesktopChromeStyle = "mac" | "windows";

/** Which window edge carries the minimise / maximise / close buttons. */
export type WindowControlsSide = "start" | "end";

/**
 * Height of the shell's own chrome row. The native buttons are ~12px tall, so
 * anything that wants to start *below* them (macOS sidebar) reserves this band.
 */
export const DESKTOP_CHROME_HEIGHT = 32;

/**
 * Horizontal space the *native* buttons occupy, by platform convention:
 * - macOS: three traffic lights on the LEFT, pinned at x=14 by the shell.
 * - Windows: three 46px caption buttons on the RIGHT (titleBarOverlay).
 *
 * The buttons are drawn by the OS above the page, so the page must keep this
 * strip empty — it cannot draw under them.
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
 * over the content column instead, so they need no band — and full screen hides
 * the macOS buttons, so the band goes with them.
 */
export function chromeTopBandPx(
  style: DesktopChromeStyle | null,
  fullscreen = false,
): number {
  return style === "mac" && !fullscreen ? DESKTOP_CHROME_HEIGHT : 0;
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
 * macOS keeps its native traffic lights and Windows its native caption buttons,
 * so both need reserved space. Linux is deliberately absent: the shell leaves
 * the system frame on there, which already carries the buttons, so the page
 * renders edge to edge.
 */
export function resolveDesktopChromeStyle(
  userAgent = navigator.userAgent,
): DesktopChromeStyle | null {
  if (/Mac|iPhone|iPad/.test(userAgent)) return "mac";
  if (/Linux|X11/.test(userAgent)) return null;
  return "windows";
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
 * `null` means "no chrome to reserve" — the browser, or Linux with its native
 * window frame.
 */
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
