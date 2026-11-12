/**
 * The payload behind the shell's failure page (``renderer/error.html``).
 *
 * The main process cannot hand a live object to a sandboxed page, so the payload
 * travels as a single query parameter and is base64url-encoded on the way out:
 * raw JSON would be re-encoded by the URL builder and mangle multi-byte CJK.
 */

export interface ShellErrorPayload {
  /** Headline of the page. Defaults to "Octop 无法启动". */
  title?: string;
  /** What happened, phrased for the user — never a bare errno or stack trace. */
  message: string;
  /** Technical tail (path, errno, failed command) shown behind "技术详情". */
  detail?: string;
  /** Shell version, printed at the bottom of the page. */
  version?: string;
}

/**
 * What a caller may supply. ``version`` is not on it: the Early Window stamps it
 * itself, so a page can never disagree with the binary that rendered it.
 */
export type ShellFailure = Omit<ShellErrorPayload, "version">;

/** Query parameter carrying the encoded payload on ``error.html``. */
export const SHELL_ERROR_PARAM = "payload";

/**
 * Upper bound for the detail block. A stack trace can run to tens of kilobytes;
 * Chromium drops URLs past ~2 MB and the disclosure would be unreadable anyway.
 */
const MAX_DETAIL_LENGTH = 4000;

export const FALLBACK_ERROR_MESSAGE = "启动过程中出现未预期的错误，请重新打开 Octop。";

function toBase64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padding = (4 - (base64.length % 4)) % 4;
  const binary = atob(base64 + "=".repeat(padding));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new TextDecoder().decode(bytes);
}

function optionalString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

export function encodeShellError(payload: ShellErrorPayload): string {
  const detail = payload.detail;
  const trimmedDetail =
    detail && detail.length > MAX_DETAIL_LENGTH ? `${detail.slice(0, MAX_DETAIL_LENGTH)}\n…` : detail;
  return toBase64Url(
    JSON.stringify({ ...payload, detail: trimmedDetail } satisfies ShellErrorPayload),
  );
}

/**
 * Decode what the main process put in the query string. Anything unusable — a
 * missing parameter, a truncated URL, hand-edited text — degrades to a generic
 * message instead of leaving the user with a blank page.
 */
export function decodeShellError(encoded: string | null | undefined): ShellErrorPayload {
  if (!encoded) return { message: FALLBACK_ERROR_MESSAGE };
  try {
    const parsed: unknown = JSON.parse(fromBase64Url(encoded));
    if (typeof parsed !== "object" || parsed === null) return { message: FALLBACK_ERROR_MESSAGE };
    const record = parsed as Record<string, unknown>;
    const message = optionalString(record.message);
    if (!message) return { message: FALLBACK_ERROR_MESSAGE };
    return {
      message,
      title: optionalString(record.title),
      detail: optionalString(record.detail),
      version: optionalString(record.version),
    };
  } catch {
    return { message: FALLBACK_ERROR_MESSAGE };
  }
}
