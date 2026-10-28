/**
 * Desktop session bridge (§7 accounts).
 *
 * Desktop builds have no password a user could type, so the shell owns a device
 * credential and can mint a fresh JWT on demand. The renderer only sees the
 * token that comes back — never the credential itself.
 *
 * On the web `window.octopDesktop` is undefined and every helper here is a
 * no-op, which is why the rest of the Dashboard needs no build flag.
 */

import {
  getDesktopBridge,
  type DesktopIssuedSession,
  type DesktopSessionBridge,
} from "../utils/desktopBridge";

export type IssuedSession = DesktopIssuedSession;

/** The shell's session bridge, when this page is running inside the app. */
function bridge(): DesktopSessionBridge | undefined {
  return getDesktopBridge()?.session;
}

/**
 * Subject claim of a JWT, used to notice a different user signing in. Returns
 * null when the token is not a decodable JWT.
 */
function subjectOf(token: string): string | null {
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const claims = JSON.parse(atob(padded)) as { sub?: unknown };
    return typeof claims.sub === "string" ? claims.sub : null;
  } catch {
    return null;
  }
}

// The credential is bound to a user, not to a token, so registering once per
// page load (per user) is enough — sliding renewal rotates the JWT constantly
// and must not trigger a write each time.
let registeredSubject: string | null = null;

/**
 * Bind the shell's device credential to the signed-in user.
 *
 * Fire-and-forget: a failure only means the next cold start falls back to the
 * login screen, which is exactly what happened before this existed.
 */
export async function registerDeviceSession(
  accessToken: string,
): Promise<void> {
  const session = bridge();
  if (!session || !accessToken) return;
  const subject = subjectOf(accessToken) ?? accessToken;
  if (registeredSubject === subject) return;
  try {
    if (await session.register(accessToken)) {
      registeredSubject = subject;
    }
  } catch {
    // Keep registeredSubject unset so the next request retries.
  }
}

/** Ask the shell for a new JWT; null when the credential is gone or refused. */
export async function renewDesktopSession(): Promise<IssuedSession | null> {
  const session = bridge();
  if (!session) return null;
  try {
    return await session.renew();
  } catch {
    return null;
  }
}
