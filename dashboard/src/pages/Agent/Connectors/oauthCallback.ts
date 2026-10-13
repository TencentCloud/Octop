/** Mirror backend public-HTTP OAuth rejection: loopback HTTP and any HTTPS are OK. */
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

export function oauthCallbackSupported(href?: string): boolean {
  const raw =
    href ??
    (typeof window !== "undefined"
      ? window.location.href
      : "https://localhost");
  try {
    const url = new URL(raw);
    const host = (url.hostname || "").toLowerCase();
    if (url.protocol === "http:" && !LOOPBACK_HOSTS.has(host)) {
      return false;
    }
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
