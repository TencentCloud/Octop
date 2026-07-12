import type { TFunction } from "i18next";

export interface ParsedApiError {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
}

/** Parse Octop API error envelope from a thrown request() Error. */
export function parseApiError(error: unknown): ParsedApiError | null {
  if (!(error instanceof Error)) return null;
  const raw = error.message;
  const jsonStart = raw.indexOf("{");
  if (jsonStart < 0) return null;
  try {
    const body = JSON.parse(raw.slice(jsonStart)) as {
      error?: {
        code?: string;
        message?: string;
        details?: Record<string, unknown>;
      };
      detail?: unknown;
      message?: string;
    };
    if (body.error && typeof body.error === "object") {
      return {
        code: typeof body.error.code === "string" ? body.error.code : undefined,
        message:
          typeof body.error.message === "string"
            ? body.error.message
            : undefined,
        details:
          body.error.details && typeof body.error.details === "object"
            ? body.error.details
            : undefined,
      };
    }
    if (typeof body.detail === "string" && body.detail.trim()) {
      return { message: body.detail };
    }
    if (typeof body.message === "string" && body.message.trim()) {
      return { message: body.message };
    }
  } catch {
    return null;
  }
  return null;
}

/**
 * Turn a failed API call into user-facing text.
 * When `t` is provided, known `apiErrors.<CODE>` keys take precedence.
 */
export function apiErrorMessage(
  error: unknown,
  fallback: string,
  t?: TFunction,
): string {
  const parsed = parseApiError(error);
  if (parsed?.code && t) {
    const key = `apiErrors.${parsed.code}`;
    const translated = t(key, parsed.details ?? {});
    if (translated !== key) return translated;
  }
  if (parsed?.message) return parsed.message;
  if (error instanceof Error && error.message.trim()) {
    const dashIdx = error.message.indexOf(" - ");
    if (dashIdx >= 0) {
      const tail = error.message.slice(dashIdx + 3).trim();
      if (tail) return tail;
    }
    return error.message;
  }
  // Plain string errors (e.g. WebSocket onError callbacks that pass a raw
  // backend-supplied message rather than throwing an Error instance).
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  return fallback;
}

/** Resolve a desktop/browser WebSocket error payload for display. */
export function wsStreamErrorMessage(
  error: { code?: string; message: string; details?: Record<string, unknown> },
  fallback: string,
  t?: TFunction,
): string {
  if (error.code && t) {
    const key = `apiErrors.${error.code}`;
    const translated = t(key, { ...(error.details ?? {}), defaultValue: "" });
    if (translated && translated !== key) return translated;
  }
  if (error.message.trim()) return error.message;
  return fallback;
}
