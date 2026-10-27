/**
 * Typed access to the Electron shell bridge injected by the desktop preload as
 * ``window.octopDesktop``. In a browser (server mode) this is absent, so the
 * Dashboard falls back to its existing Python self-update flow.
 */

export interface DesktopClientSettings {
  launchAtLogin: boolean;
  closeBehavior: "quit" | "tray";
  themeBackground: "system" | "light" | "dark";
  stableOnly: boolean;
}

export interface DesktopUpdateCheckResult {
  status: "update-available" | "up-to-date" | "error";
  currentVersion: string;
  latestVersion: string | null;
  error: string | null;
}

export interface DesktopPlatformInfo {
  platform: "darwin" | "win32" | "linux";
  arch: string;
  isDesktop: true;
}

/**
 * A JWT minted by the shell from its stored device credential. The credential
 * itself never crosses the bridge.
 */
export interface DesktopIssuedSession {
  access_token: string;
  expires_in: number;
}

export interface DesktopSessionBridge {
  /** Bind the credential to the signed-in user; false when the shell refused. */
  register(accessToken: string): Promise<boolean>;
  /** Mint a fresh JWT, or null when this install has no usable credential. */
  renew(): Promise<DesktopIssuedSession | null>;
  /** Forget this install's credential. */
  revoke(accessToken: string): Promise<boolean>;
}

export interface OctopDesktopBridge {
  session?: DesktopSessionBridge;
  getPlatformInfo(): Promise<DesktopPlatformInfo>;
  openDirectoryPicker(): Promise<string | null>;
  openFilePicker(): Promise<string | null>;
  onBackendReady(callback: (ready: { ok: boolean }) => void): () => void;
  windowControls(action: "minimize" | "maximize" | "close"): void;
  clientSettings: {
    get(): Promise<DesktopClientSettings>;
    set(patch: Partial<DesktopClientSettings>): Promise<DesktopClientSettings>;
  };
  checkForUpdates(): Promise<DesktopUpdateCheckResult>;
  openUpdateConfirmation(): Promise<void>;
}

declare global {
  interface Window {
    octopDesktop?: OctopDesktopBridge;
  }
}

export function isDesktopShell(): boolean {
  return (
    typeof window !== "undefined" && typeof window.octopDesktop !== "undefined"
  );
}

export function getDesktopBridge(): OctopDesktopBridge | null {
  return isDesktopShell() ? window.octopDesktop! : null;
}
