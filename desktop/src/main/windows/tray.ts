import { join } from "node:path";

/**
 * Windows notification-area icon. The dashboard close button hides the window;
 * this icon opens it again. macOS uses the Dock for the same job.
 *
 * Matches `appId` in `electron-builder.config.ts`. Windows groups the tray
 * icon and the taskbar button under this id.
 */
export const WINDOWS_APP_USER_MODEL_ID = "com.tencent.octop";

export function shouldInstallSystemTray(platform: string): boolean {
  return platform === "win32";
}

export interface TrayIconCandidates {
  platform: string;
  isPackaged: boolean;
  resourcesDir: string;
  execPath: string;
}

/**
 * Dev keeps `resources/icon.ico`. A packaged NSIS build embeds that icon in
 * the exe and does not copy the file out, so the exe is the fallback.
 */
export function trayIconCandidates(input: TrayIconCandidates): string[] {
  if (input.platform !== "win32") return [];
  const bundled = join(input.resourcesDir, "icon.ico");
  return input.isPackaged ? [bundled, input.execPath] : [bundled];
}

export interface TrayMenuLabels {
  show: string;
  quit: string;
}

export function trayMenuLabels(locale: string): TrayMenuLabels {
  if (locale.toLowerCase().startsWith("zh")) {
    return { show: "显示窗口", quit: "退出" };
  }
  return { show: "Show window", quit: "Quit" };
}
