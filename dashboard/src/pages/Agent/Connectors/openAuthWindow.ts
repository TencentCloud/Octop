import { isDesktopShell } from "../../../utils/desktopBridge";

/** System browser on desktop; a new tab in the web dashboard. */
export function openExternalBrowserUrl(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer");
}

/**
 * The Electron shell routes ``_blank`` targets to the OS browser, so the auth
 * flow runs there and the app keeps polling for completion — a placeholder
 * popup would only be opened and immediately handed off.
 */
export function tryOpenAuthPopup(
  url: string,
  name: string,
  features: string,
): Window | null {
  if (isDesktopShell()) return null;
  return window.open(url, name, features);
}

export function isAuthPopupBlocked(popup: Window | null): boolean {
  return popup == null && !isDesktopShell();
}

export function navigateAuthWindow(
  popup: Window | null,
  url: string | null | undefined,
): void {
  if (!url) return;
  if (!isDesktopShell() && popup && !popup.closed) {
    try {
      popup.location.replace(url);
      popup.focus();
      return;
    } catch {
      // Fall through to a fresh open.
    }
  }
  openExternalBrowserUrl(url);
}
