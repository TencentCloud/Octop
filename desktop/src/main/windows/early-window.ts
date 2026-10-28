import { app, BrowserWindow } from "electron";

import { encodeShellError, SHELL_ERROR_PARAM, type ShellFailure } from "../../shared/shell-error";
import { windowChrome } from "./chrome";

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
}

export interface EarlyWindow {
  /** Replace the splash with the failure Result — same window, no white flash. */
  showError(failure: ShellFailure): void;
  close(): void;
}

export function createEarlyWindow(options: EarlyWindowOptions): EarlyWindow {
  const win = new BrowserWindow({
    width: 1080,
    height: 720,
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
    },
  });
  win.once("ready-to-show", () => win.show());
  void win.loadFile(options.splashFile);

  return {
    /**
     * The payload rides in the query string because the page is sandboxed: it has
     * no preload, no IPC and no Node access, so this is the only channel the shell
     * and its own page share.
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
