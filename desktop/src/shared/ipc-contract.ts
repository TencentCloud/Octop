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

/** A JWT minted by the shell from the stored device credential. */
export interface IssuedSession {
  access_token: string;
  expires_in: number;
}

/**
 * Loopback WebSocket relay (§5.2). A custom scheme cannot carry a handshake,
 * so the page dials this instead of ``octop://app/api/…``.
 */
export interface WsRelayEndpoint {
  /** ``ws://127.0.0.1:<port>/<token>`` — append ``/api/…`` to it. */
  baseUrl: string;
  /** Random per-launch path segment; the relay refuses every other path. */
  token: string;
}

/** Theme for the *native* window controls (traffic lights / caption buttons). */
export interface WindowChromeTheme {
  /** Resolved mode the page is showing. */
  mode: "light" | "dark";
  /** The user's preference; kept so "system" keeps following the OS. */
  scheme?: "system" | "light" | "dark";
}

export const IPC_CHANNELS = {
  getPlatformInfo: "octop:get-platform-info",
  openDirectoryPicker: "octop:open-directory-picker",
  openFilePicker: "octop:open-file-picker",
  onBackendReady: "octop:backend-ready",
  windowChromeTheme: "octop:window-chrome-theme",
  windowChromeFullscreen: "octop:window-chrome-fullscreen",
  clientSettingsGet: "octop:client-settings:get",
  clientSettingsSet: "octop:client-settings:set",
  wsEndpoint: "octop:ws-endpoint",
  checkForUpdates: "octop:check-for-updates",
  openUpdateConfirmation: "octop:open-update-confirmation",
  sessionRegister: "octop:session:register",
  sessionRenew: "octop:session:renew",
  sessionRevoke: "octop:session:revoke",
} as const;
