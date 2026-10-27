/**
 * Shared IPC contract between main and preload. The renderer only ever sees the
 * typed ``window.octopDesktop`` bridge; raw ``ipcRenderer`` is never exposed.
 */

export interface ClientSettings {
  /** Launch at login / open at login. */
  launchAtLogin: boolean;
  /** Close-window behaviour: quit vs. keep in tray. */
  closeBehavior: "quit" | "tray";
  /** Early-window theme background ("system" | "light" | "dark"). */
  themeBackground: "system" | "light" | "dark";
  /** Whether the shell update check should follow the stable channel only. */
  stableOnly: boolean;
}

export interface PlatformInfo {
  platform: "darwin" | "win32" | "linux";
  arch: string;
  isDesktop: true;
}

export interface UpdateCheckResult {
  status: "update-available" | "up-to-date" | "error";
  currentVersion: string;
  latestVersion: string | null;
  error: string | null;
}

export const IPC_CHANNELS = {
  getPlatformInfo: "octop:get-platform-info",
  openDirectoryPicker: "octop:open-directory-picker",
  openFilePicker: "octop:open-file-picker",
  onBackendReady: "octop:backend-ready",
  windowControl: "octop:window-control",
  clientSettingsGet: "octop:client-settings:get",
  clientSettingsSet: "octop:client-settings:set",
  checkForUpdates: "octop:check-for-updates",
  openUpdateConfirmation: "octop:open-update-confirmation",
} as const;

export type WindowControlAction = "minimize" | "maximize" | "close";
