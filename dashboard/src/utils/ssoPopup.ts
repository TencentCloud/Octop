export const SSO_MESSAGE_TYPE = "octop-sso";

export type SsoPopupMessage = {
  type: typeof SSO_MESSAGE_TYPE;
  ok: boolean;
  redirect?: string;
  bind?: boolean;
  error?: string;
  /** Present on successful login popups so the opener can store session-only tokens. */
  access_token?: string;
  remember?: boolean;
};

export function isSsoPopup(): boolean {
  try {
    if (!window.opener || window.opener.closed) return false;
    // Only treat as SSO popup if opener is same-origin (trusted Octop page).
    // Cross-origin openers (e.g. enterprise portal links without rel="noopener")
    // cannot speak our octop-sso protocol — don't close the tab on their
    // behalf, otherwise the user's login succeeds server-side but the popup
    // closes before the complete page can save the session (#2347).
    try {
      return window.opener.location.origin === window.location.origin;
    } catch {
      // Cross-origin — browsers throw when reading opener.location.origin;
      // this is not an Octop-launched popup.
      return false;
    }
  } catch {
    return false;
  }
}

export function notifySsoOpener(
  payload: Omit<SsoPopupMessage, "type">,
): boolean {
  if (!isSsoPopup()) return false;
  const message: SsoPopupMessage = { type: SSO_MESSAGE_TYPE, ...payload };
  window.opener.postMessage(message, window.location.origin);
  window.close();
  return true;
}

export function openSsoPopup(): Window | null {
  return window.open(
    "about:blank",
    "octop-sso",
    "popup=yes,width=520,height=720,noopener=no",
  );
}

export function isSsoPopupMessage(
  event: MessageEvent,
  expectedOrigin: string,
): event is MessageEvent<SsoPopupMessage> {
  return (
    event.origin === expectedOrigin &&
    typeof event.data === "object" &&
    event.data !== null &&
    event.data.type === SSO_MESSAGE_TYPE
  );
}
