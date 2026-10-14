import type { BridgeConnection } from "../../../api/modules/bridge";

function isLoopbackHost(host: string): boolean {
  const normalized = host
    .trim()
    .toLowerCase()
    .replace(/^\[|\]$/g, "");
  return (
    normalized === "localhost" ||
    normalized === "127.0.0.1" ||
    normalized === "::1" ||
    normalized === "0.0.0.0"
  );
}

/** Short address for a card: hostname, plus a non-default port. */
export function peerHostLabel(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(value)
    ? value
    : `http://${value}`;
  try {
    const url = new URL(withScheme);
    const host = url.hostname;
    if (!host) return value;
    const port = url.port;
    if (port && port !== "80" && port !== "443") return `${host}:${port}`;
    return host;
  } catch {
    return value;
  }
}

function hostFromUrl(url: string): string {
  const raw = url.trim();
  if (!raw) return "";
  try {
    return new URL(raw).hostname;
  } catch {
    return "";
  }
}

/** Address line for an inbound card: public advertise URL, otherwise the observed IP. */
export function inboundPeerAddress(row: BridgeConnection): string {
  const ip = (row.peer_client_host || "").trim();
  const url = (row.peer_base_url || "").trim();
  const urlHost = hostFromUrl(url);
  if (url && urlHost && !isLoopbackHost(urlHost)) return url;
  if (ip) return ip;
  return url;
}

/** Extra IP line when the address above is a different public URL. */
export function inboundSourceIp(row: BridgeConnection): string {
  const ip = (row.peer_client_host || "").trim();
  if (!ip || isLoopbackHost(ip)) return "";
  const address = inboundPeerAddress(row);
  if (!address || address === ip) return "";
  const host = hostFromUrl(address);
  if (host && host === ip) return "";
  return ip;
}
