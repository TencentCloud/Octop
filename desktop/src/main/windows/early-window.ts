import { BrowserWindow } from "electron";

/**
 * Early Window (§4): shown immediately so the cold start never shows a blank
 * screen. It renders a lightweight splash and is swapped for the real Dashboard
 * only after ``/api/health`` reports the sidecar is ready.
 */

/**
 * The splash is always white, independent of the app theme: it is the first
 * frame the user sees, before the dashboard CSS has loaded, so it must not
 * depend on a setting that has not been applied to the page yet.
 */
export const EARLY_WINDOW_BACKGROUND = "#ffffff";

export function createEarlyWindow(
  options: { splashFile: string },
): BrowserWindow {
  const win = new BrowserWindow({
    width: 1080,
    height: 720,
    show: false,
    frame: false,
    backgroundColor: EARLY_WINDOW_BACKGROUND,
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.once("ready-to-show", () => win.show());
  void win.loadFile(options.splashFile);
  return win;
}

/** Render a run-time error (e.g. manual downgrade) inside the same window. */
export function showEarlyWindowError(win: BrowserWindow, message: string): void {
  void win.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(
      `<html><body style="font-family:system-ui;padding:48px;color:#111;background:#fff"><h2>Octop 无法启动</h2><pre style="white-space:pre-wrap">${message}</pre></body></html>`,
    )}`,
  );
}
