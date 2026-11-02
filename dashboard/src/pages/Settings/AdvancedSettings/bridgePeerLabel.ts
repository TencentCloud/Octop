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

const MASK_DOT = "•";

/** Fixed-width dot run: the masked length must not leak the real length. */
function maskDots(count: number): string {
  return MASK_DOT.repeat(count);
}

/**
 * Keep the first and last `keep` characters.
 * Values too short to hide anything degrade to their first character.
 */
function maskMiddle(value: string, keep: number): string {
  const chars = Array.from(value);
  if (chars.length <= keep * 2 + 1) {
    return chars.length > 1 ? `${chars[0]}${maskDots(2)}` : MASK_DOT;
  }
  return `${chars.slice(0, keep).join("")}${maskDots(6)}${chars
    .slice(-keep)
    .join("")}`;
}

function maskIpv4(value: string): string {
  const parts = value.split(".");
  if (parts.length !== 4) return maskMiddle(value, 2);
  return `${parts[0]}.${maskDots(3)}.${maskDots(3)}.${parts[3]}`;
}

function maskHost(host: string): string {
  const value = host.trim().replace(/^\[|\]$/g, "");
  if (!value) return "";
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) return maskIpv4(value);
  // IPv6 has no meaningful first/last slice to keep.
  if (value.includes(":")) return maskDots(4);
  return maskMiddle(value.toLowerCase(), 2);
}

/**
 * Mask a peer address (URL, host:port or bare IP) for screen-share safety.
 * Keeps the scheme and port so connections stay distinguishable, and masks
 * the host: first/last two characters, or the middle two octets for IPv4.
 * Display only — the underlying connection data is never altered.
 */
export function maskPeerAddress(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  const hasScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(value);
  try {
    const url = new URL(hasScheme ? value : `http://${value}`);
    const host = url.hostname;
    if (!host) return maskMiddle(value, 2);
    const port =
      url.port && url.port !== "80" && url.port !== "443" ? `:${url.port}` : "";
    const scheme = hasScheme ? url.protocol : "";
    return `${scheme}${scheme ? "//" : ""}${maskHost(host)}${port}`;
  } catch {
    return maskMiddle(value, 2);
  }
}

/**
 * Mask a peer account: first and last two characters; accounts shorter than
 * six characters keep only their first character.
 */
export function maskPeerAccount(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  return maskMiddle(value, 2);
}
