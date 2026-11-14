/**
 * WebSocket addresses under the desktop shell (§5.2).
 *
 * The shell serves the Dashboard from the privileged ``octop://app/`` scheme,
 * which cannot carry a WebSocket handshake — Chromium's upgrade never reaches a
 * protocol handler, and a request redirect is dropped. So the shell runs a
 * loopback relay and tells the page where it listens; the page dials that
 * instead of its own origin.
 *
 * Everywhere else — a browser tab, a server deployment — there is no bridge, and
 * the address keeps coming from the page origin. That is why this module must
 * never throw: it sits inside URL builders that run during render.
 */

import { getDesktopBridge } from "./desktopBridge";

interface RelayEndpoint {
  baseUrl: string;
  token: string;
}

/** Read once: the shell binds the relay before the window loads, and its
 *  address cannot change during a launch. */
let cached: RelayEndpoint | null | undefined;

function relay(): RelayEndpoint | null {
  if (cached === undefined) {
    cached = getDesktopBridge()?.wsEndpoint?.() ?? null;
  }
  return cached;
}

/** ``ws://127.0.0.1:<port>/<token>``, or null outside the desktop shell. */
export function desktopWsBase(): string | null {
  return relay()?.baseUrl ?? null;
}

/**
 * Full WebSocket URL for an ``/api/…`` path (e.g. ``/api/mobile-stream/ws``).
 * Callers append their own query string afterwards, exactly as they did with the
 * page-origin form, so no query escaping is duplicated here.
 */
export function resolveWsUrl(apiPath: string): string {
  const base = relay()?.baseUrl;
  if (base) return `${base}${apiPath}`;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${apiPath}`;
}
