export const SSO_MESSAGE_TYPE = "octop-sso";

export type SsoPopupMessage = {
  type: typeof SSO_MESSAGE_TYPE;
  ok: boolean;
  redirect?: string;
  bind?: boolean;
  error?: string;
};

export function isSsoPopup(): boolean {
  try {
    return Boolean(window.opener && !window.opener.closed);
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
