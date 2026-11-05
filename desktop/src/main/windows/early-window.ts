import { app, BrowserWindow, ipcMain } from "electron";

import { EARLY_IPC } from "../../shared/early-ipc";
import { encodeShellError, SHELL_ERROR_PARAM, type ShellFailure } from "../../shared/shell-error";
import {
  concealWindowsMenuBar,
  windowBackground,
  windowChrome,
  type WindowChromeTheme,
} from "./chrome";
import { DEFAULT_WINDOW_SIZE, MIN_WINDOW_SIZE } from "./size";

/**
 * Early Window (§4): shown immediately so the cold start never shows a blank
 * screen. The same window loads the Dashboard once ``/api/health`` is green.
 * It is not closed and replaced.
 */

export interface EarlyWindowOptions {
  /** Splash page (``renderer/splash.html``). */
  splashFile: string;
  /** Failure Result page (``renderer/error.html``). */
  errorFile: string;
  /** Stamped onto the failure page so a report always names the running build. */
  version: string;
  /**
   * Device light/dark preference, already resolved. The splash cannot read the
   * Dashboard's localStorage (different origin), so the colour has to arrive
   * with the page URL.
   */
  theme: WindowChromeTheme;
  /** ``preload/early.js`` — the one-method bridge these pages are allowed. */
  preload?: string;
}

export interface EarlyWindow {
  /** Replace the splash with the failure Result — same window, no blank frame. */
  showError(failure: ShellFailure): void;
  /** The window the user already has open. Later steps load into it. */
  readonly browserWindow: BrowserWindow;
  close(): void;
}

export function createEarlyWindow(options: EarlyWindowOptions): EarlyWindow {
  registerRelaunchHandler();
  const mode = options.theme.mode;

  const win = new BrowserWindow({
    title: "Octop",
    width: DEFAULT_WINDOW_SIZE.width,
    height: DEFAULT_WINDOW_SIZE.height,
    // Same floor as the Dashboard: this window becomes the Dashboard, so a
    // size the page would refuse has to be refused here too.
    minWidth: MIN_WINDOW_SIZE.width,
    minHeight: MIN_WINDOW_SIZE.height,
    show: false,
    // Same native chrome as the Dashboard window, so the swap from splash to
    // Dashboard does not move the traffic lights / caption buttons. Glyph colour
    // follows the resolved device theme, same as the page background.
    ...windowChrome(mode),
    backgroundColor: windowBackground(mode),
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      ...(options.preload ? { preload: options.preload } : {}),
    },
  });
  // Before the first paint: the splash is a loading page and draws no menu.
  concealWindowsMenuBar(win);
  win.once("ready-to-show", () => {
    concealWindowsMenuBar(win);
    win.show();
  });
  // The splash names the build it is starting; the failure page gets the same
  // value in its payload so the two can never disagree. `theme` is the resolved
  // mode — the page is static and does not track a later OS change.
  void win.loadFile(options.splashFile, {
    query: { version: options.version, theme: mode },
  });

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
      void win.loadFile(options.errorFile, {
        query: { [SHELL_ERROR_PARAM]: payload, theme: mode },
      });
    },
    browserWindow: win,
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
