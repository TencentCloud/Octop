import { BrowserWindow } from "electron";

import { IPC_CHANNELS } from "../../shared/ipc-contract";
import {
  concealWindowsMenuBar,
  isAppNavigation,
  setWindowsCaptionVisible,
  windowChrome,
  type WindowChromeTheme,
} from "./chrome";
import { DEFAULT_WINDOW_SIZE, MIN_WINDOW_SIZE } from "./size";

/**
 * The real Dashboard window. Packaged builds load ``octop://app/`` (static
 * files, API proxied in the main process). Local dev loads the Vite server so
 * the page hot-reloads. Sandbox flags stay the same either way (§5.3).
 */

/** In-app navigation and fullscreen signals. Safe to call on the splash window before it loads the Dashboard. */
export function installDashboardGuards(
  win: BrowserWindow,
  options: { appOrigin: string; onNavigate: (url: string) => void },
): void {
  // External navigation is intercepted and opened by the OS, never in-app (§5.2).
  win.webContents.setWindowOpenHandler(({ url }) => {
    options.onNavigate(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!isAppNavigation(url, options.appOrigin)) {
      event.preventDefault();
      options.onNavigate(url);
    }
  });

  // Fullscreen hides the native buttons (traffic lights / caption overlay).
  // The page keeps its menu row and drops the space those buttons occupied.
  const sendFullscreen = (fullscreen: boolean) => {
    if (win.isDestroyed() || win.webContents.isDestroyed()) return;
    win.webContents.send(IPC_CHANNELS.windowChromeFullscreen, fullscreen);
  };
  win.on("enter-full-screen", () => {
    setWindowsCaptionVisible(win, false);
    sendFullscreen(true);
  });
  win.on("leave-full-screen", () => {
    setWindowsCaptionVisible(win, true);
    sendFullscreen(false);
  });
}

export function createMainWindow(options: {
  preload: string;
  backgroundColor: string;
  /** Native-control theme; the page's own theme is reported over IPC later. */
  theme: WindowChromeTheme;
  /** Full URL of the Dashboard document, including the theme query. */
  entryUrl: string;
  /** Origin that may navigate in-app. Anything else opens in the OS browser. */
  appOrigin: string;
  onNavigate: (url: string) => void;
}): BrowserWindow {
  const win = new BrowserWindow({
    title: "Octop",
    width: DEFAULT_WINDOW_SIZE.width,
    height: DEFAULT_WINDOW_SIZE.height,
    // The Dashboard stops being usable below its desktop breakpoint, so the
    // window refuses to shrink past it instead of letting the user do it.
    minWidth: MIN_WINDOW_SIZE.width,
    minHeight: MIN_WINDOW_SIZE.height,
    show: false,
    // macOS pins traffic lights over the page. Windows overlays transparent
    // caption buttons on the menu row. Linux keeps that hidden title bar, and
    // the page draws square buttons in the same corner.
    ...windowChrome(options.theme.mode),
    backgroundColor: options.backgroundColor,
    webPreferences: {
      preload: options.preload,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });

  installDashboardGuards(win, options);

  // The boot splash (#octop-boot) is still the loading page. The page menu
  // appears only after React replaces that splash.
  concealWindowsMenuBar(win);
  win.once("ready-to-show", () => {
    concealWindowsMenuBar(win);
    win.show();
  });
  // The boot script reads this once, writes it into localStorage, then strips
  // the query. Passing the preference (not the resolved mode) keeps "system"
  // tracking the OS after the page is up.
  void win.loadURL(options.entryUrl);
  return win;
}
