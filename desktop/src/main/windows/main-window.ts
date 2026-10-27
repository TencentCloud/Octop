import { BrowserWindow } from "electron";

/**
 * The real Dashboard window loads ``octop://app/`` — the custom privileged
 * protocol — with the strictest sandbox flags (§5.3). Static assets are served
 * from the bundled Dashboard build, API calls are proxied by the main process.
 */

export function createMainWindow(options: {
  preload: string;
  backgroundColor: string;
  onNavigate: (url: string) => void;
}): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    // The Dashboard draws the whole chrome (traffic lights / caption buttons)
    // and drags via `-webkit-app-region`, so the native frame is off.
    frame: false,
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

  win.once("ready-to-show", () => win.show());
  void win.loadURL("octop://app/");
  return win;
}
