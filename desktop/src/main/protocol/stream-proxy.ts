/**
 * Reverse-proxy the ``octop://app/api/*`` path to the loopback sidecar (§5.2).
 *
 * The renderer never learns the real port or any credential. The main process
 * strips hop-by-hop / connection-level headers and forwards the stream with
 * backpressure, so SSE and streaming responses are not buffered in memory.
 */

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

/** Headers we always drop on the way to the backend (spoofable connection state). */
const STRIP_REQUEST = new Set(["host", "origin", "cookie", "content-length"]);

export function sanitizeForwardHeaders(headers: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (HOP_BY_HOP.has(lower)) return;
    if (STRIP_REQUEST.has(lower)) return;
    out[key] = value;
  });
  return out;
}

/** Map ``octop://app/api/...`` to ``http://127.0.0.1:<port>/api/...``. */
export function toBackendUrl(port: number, pathname: string, search: string): string {
  const rest = pathname.replace(/^\/api/, "");
  return `http://127.0.0.1:${port}/api${rest}${search}`;
}

/** Only the app's own ``/api/*`` route is proxied — everything else is static. */
export function isApiPath(pathname: string): boolean {
  return pathname === "/api" || pathname.startsWith("/api/");
}
