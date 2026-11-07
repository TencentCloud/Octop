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
 * Dev and packaged builds both keep `resources/icon.ico` (the package copies
 * it next to the app). The executable is not an image file; it is only a
 * Shell-icon fallback when that ico is missing.
 */
export function trayIconCandidates(input: TrayIconCandidates): string[] {
  if (input.platform !== "win32") return [];
  const bundled = join(input.resourcesDir, "icon.ico");
  return input.isPackaged ? [bundled, input.execPath] : [bundled];
}

/** First real image file among the candidates. Skips the executable fallback. */
export function trayIconImagePath(
  candidates: readonly string[],
  exists: (path: string) => boolean,
): string | null {
  for (const candidate of candidates) {
    if (candidate.toLowerCase().endsWith(".exe")) continue;
    if (exists(candidate)) return candidate;
  }
  return null;
}

/** Packaged executable, for `app.getFileIcon` when the ico file is absent. */
export function trayExecutableFallback(candidates: readonly string[]): string | null {
  return candidates.find((candidate) => candidate.toLowerCase().endsWith(".exe")) ?? null;
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
