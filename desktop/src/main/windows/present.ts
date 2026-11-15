/**
 * Putting a window back on screen when the user clicks the Dock (macOS
 * `activate`) or launches the app a second time. The process often outlives
 * the window, so the click has to show the one that is already open.
 */

export interface PresentableWindow {
  isDestroyed(): boolean;
  isMinimized(): boolean;
  restore(): void;
  show(): void;
  focus(): void;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Enough of the window must sit on a display to count as visible. */
const MIN_VISIBLE_PX = 80;

/**
 * With the tray close setting, the close button hides the window instead of
 * ending the process. macOS comes back from the Dock. Windows and Linux come
 * back from the tray icon, and only when that icon exists — hiding with no
 * icon would leave the window unreachable. Quit lets the close finish.
 */
export function shouldKeepWindowOnClose(input: {
  platform: string;
  closeBehavior: "quit" | "tray";
  quitting: boolean;
  /** Windows and Linux. `true` once the tray icon is on screen. */
  trayReady?: boolean;
}): boolean {
  if (input.quitting || input.closeBehavior !== "tray") return false;
  if (input.platform === "darwin") return true;
  if (input.platform === "win32" || input.platform === "linux") return input.trayReady === true;
  return false;
}

/**
 * True when at least `MIN_VISIBLE_PX` of `bounds` overlaps a display work area.
 * A window parked on a disconnected monitor fails this and should be centered.
 */
export function isWindowOnScreen(bounds: Rect, workAreas: readonly Rect[]): boolean {
  return workAreas.some((area) => {
    const overlapWidth =
      Math.min(bounds.x + bounds.width, area.x + area.width) - Math.max(bounds.x, area.x);
    const overlapHeight =
      Math.min(bounds.y + bounds.height, area.y + area.height) - Math.max(bounds.y, area.y);
    return overlapWidth >= MIN_VISIBLE_PX && overlapHeight >= MIN_VISIBLE_PX;
  });
}

/**
 * Restore, show, and focus every live window. A minimized or hidden window is
 * still in this list; Dock click does not recreate it. Returns how many were
 * brought forward.
 */
export function presentWindows(windows: readonly PresentableWindow[]): number {
  let shown = 0;
  for (const win of windows) {
    if (win.isDestroyed()) continue;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
    shown += 1;
  }
  return shown;
}
