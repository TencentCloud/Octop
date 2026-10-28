import { app, BrowserWindow, ipcMain } from "electron";

import { EARLY_IPC } from "../../shared/early-ipc";
import { encodeShellError, SHELL_ERROR_PARAM, type ShellFailure } from "../../shared/shell-error";
import { windowChrome } from "./chrome";
import { MIN_WINDOW_SIZE } from "./size";

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

export interface EarlyWindowOptions {
  /** Splash page (``renderer/splash.html``). */
  splashFile: string;
  /** Failure Result page (``renderer/error.html``). */
  errorFile: string;
  /** Stamped onto the failure page so a report always names the running build. */
  version: string;
  /** ``preload/early.js`` — the one-method bridge these pages are allowed. */
  preload?: string;
}

export interface EarlyWindow {
  /** Replace the splash with the failure Result — same window, no white flash. */
  showError(failure: ShellFailure): void;
  close(): void;
}

export function createEarlyWindow(options: EarlyWindowOptions): EarlyWindow {
  registerRelaunchHandler();

  const win = new BrowserWindow({
    width: 1080,
    height: 720,
    // Same floor as the Dashboard window: the splash swaps for it in place, so
    // a size the Dashboard would refuse has to be refused here too.
    minWidth: MIN_WINDOW_SIZE.width,
    minHeight: MIN_WINDOW_SIZE.height,
    show: false,
    // Same native chrome as the Dashboard window, so the swap from splash to
    // Dashboard does not move the traffic lights / caption buttons. The splash
    // is white regardless of the app theme, so the glyphs are the light ones.
    ...windowChrome("light"),
    backgroundColor: EARLY_WINDOW_BACKGROUND,
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      ...(options.preload ? { preload: options.preload } : {}),
    },
  });
  win.once("ready-to-show", () => win.show());
  // The splash names the build it is starting; the failure page gets the same
  // value in its payload so the two can never disagree.
  void win.loadFile(options.splashFile, { query: { version: options.version } });

  return {
    /**
     * The payload rides in the query string because the page is sandboxed: it
     * gets the one-method preload bridge and nothing else, so a URL is the only
     * channel the shell and its own page share for structured data.
     */
    showError(failure: ShellFailure): void {
      const payload = encodeShellError({ ...failure, version: options.version });
      // Dismissing the failure page ends the launch: on macOS the app would
      // otherwise idle in the Dock with no window and nothing left to show.
      win.once("closed", () => app.quit());
      void win.loadFile(options.errorFile, { query: { [SHELL_ERROR_PARAM]: payload } });
    },
    close(): void {
      if (!win.isDestroyed()) win.close();
    },
  };
}

let relaunchHandlerRegistered = false;

/**
 * "重试" on the failure page. Most boot failures are transient (a busy port, a
 * sidecar that lost a race), and the alternative — quit, find the icon, open it
 * again — is exactly the friction a failure page should remove. ``relaunch``
 * queues a fresh process before this one exits, so the new instance starts from
 * a clean slate rather than re-entering a half-finished boot.
 */
function registerRelaunchHandler(): void {
  if (relaunchHandlerRegistered) return;
  relaunchHandlerRegistered = true;
  ipcMain.on(EARLY_IPC.restart, () => {
    app.relaunch();
    app.exit(0);
  });
}
