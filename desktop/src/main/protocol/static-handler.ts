import { resolve, sep } from "node:path";

/**
 * Pure helpers for the ``octop://app/`` static handler (§5.2). Actual request
 * serving happens in the main process using Electron's ``protocol.handle`` and
 * ``net.fetch``; these functions are dependency-free so they can be unit-tested.
 */

/** Resolve a request path to a file inside ``root``, or ``null`` if it escapes. */
export function resolveStaticPath(root: string, pathname: string): string | null {
  let rel = decodeURIComponent(pathname.replace(/^\/+/, ""));
  if (rel === "" || rel === ".") rel = "index.html";
  if (!rel.includes(".")) rel = rel.replace(/\/?$/, "/index.html");
  const abs = resolve(root, rel);
  const rootWithSep = root.endsWith(sep) ? root : root + sep;
  if (abs !== root && !abs.startsWith(rootWithSep)) return null;
  return abs;
}

export function isExternalLink(url: string): boolean {
  return /^https?:\/\//i.test(url) && !/^http:\/\/127\.0\.0\.1/i.test(url);
}

const MIME: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".map": "application/json",
};

export function contentTypeFor(path: string): string {
  const dot = path.lastIndexOf(".");
  if (dot === -1) return "application/octet-stream";
  return MIME[path.slice(dot).toLowerCase()] ?? "application/octet-stream";
}
