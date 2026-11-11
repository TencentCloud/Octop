import { resolveWsUrl } from "../utils/desktopWsUrl";
import { routerBasename } from "../utils/publicUrl";

declare const BASE_URL: string;

/**
 * Get the full API URL with /api prefix
 * @param path - API path (e.g., "/models", "/skills")
 * @returns Full API URL (e.g., "http://localhost:8088/api/models" or "/api/models")
 */
export function getApiUrl(path: string): string {
  // Absolute API host (define BASE_URL) wins; otherwise Vite public base.
  const base = BASE_URL || routerBasename() || "";
  const apiPrefix = "/api";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${apiPrefix}${normalizedPath}`;
}

/**
 * Get a WebSocket URL derived from the same origin as the API.
 * Converts http:// → ws:// and https:// → wss://.
 * If BASE_URL is empty (same-origin), uses the current page location.
 * @param path - API path (e.g., "/browser-stream/ws")
 * @returns Full WebSocket URL
 */
export function getWsUrl(path: string): string {
  const base = BASE_URL || routerBasename() || "";
  const apiPrefix = "/api";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const httpUrl = `${base}${apiPrefix}${normalizedPath}`;

  if (httpUrl.startsWith("http://")) {
    return httpUrl.replace("http://", "ws://");
  }
  if (httpUrl.startsWith("https://")) {
    return httpUrl.replace("https://", "wss://");
  }

  // Relative URL — derive from the page origin, or from the shell's relay when
  // the page is served by the desktop shell (§5.2).
  return resolveWsUrl(httpUrl);
}
