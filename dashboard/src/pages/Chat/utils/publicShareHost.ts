/** True when a share URL built from this host only works on this machine. */
export function isLoopbackShareHost(hostname: string): boolean {
  const host = hostname
    .trim()
    .toLowerCase()
    .replace(/^\[|\]$/g, "");
  if (!host) return false;
  if (host === "localhost" || host.endsWith(".localhost")) return true;
  if (host === "::1" || host === "0.0.0.0") return true;
  if (!host.startsWith("127.")) return false;
  const parts = host.split(".");
  return (
    parts.length === 4 &&
    parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)
  );
}

/** Share links are useful only when the page itself is not on a loopback host. */
export function publicShareAvailable(hostname?: string): boolean {
  const host =
    hostname ?? (typeof window === "undefined" ? "" : window.location.hostname);
  return !isLoopbackShareHost(host);
}
