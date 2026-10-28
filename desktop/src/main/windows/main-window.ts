import { BrowserWindow } from "electron";

import { IPC_CHANNELS } from "../../shared/ipc-contract";
import { windowChrome, type WindowChromeTheme } from "./chrome";

/**
 * The real Dashboard window loads ``octop://app/`` — the custom privileged
 * protocol — with the strictest sandbox flags (§5.3). Static assets are served
 * from the bundled Dashboard build, API calls are proxied by the main process.
 */

export function createMainWindow(options: {
  preload: string;
  backgroundColor: string;
  /** Native-control theme; the page's own theme is reported over IPC later. */
  theme: WindowChromeTheme;
  onNavigate: (url: string) => void;
}): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    // The chrome is native (macOS traffic lights / Windows caption buttons), so
    // the Dashboard only reserves space for it and drags via `app-region`.
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

  // External navigation is intercepted and opened by the OS, never in-app (§5.2).
  win.webContents.setWindowOpenHandler(({ url }) => {
    options.onNavigate(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("octop://app")) {
      event.preventDefault();
      options.onNavigate(url);
    }
  });

  // macOS hides the traffic lights in full screen, so the page has to stop
  // reserving room for them. Nothing else changes: the buttons stay native.
  const sendFullscreen = (fullscreen: boolean) => {
    if (win.isDestroyed() || win.webContents.isDestroyed()) return;
    win.webContents.send(IPC_CHANNELS.windowChromeFullscreen, fullscreen);
  };
  win.on("enter-full-screen", () => sendFullscreen(true));
  win.on("leave-full-screen", () => sendFullscreen(false));

  win.once("ready-to-show", () => win.show());
  void win.loadURL("octop://app/");
  return win;
}
