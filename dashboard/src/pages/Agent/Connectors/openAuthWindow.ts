import { isDesktopShell } from "../../../utils/desktopChrome";

/** System browser on desktop; a new tab in the web dashboard. */
export function openExternalBrowserUrl(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer");
}

/** Named popups do not appear in the Wails WebView. */
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
