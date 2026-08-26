import { useEffect, useState } from "react";
import { octopSettingsApi } from "../api/modules/settings";

export const DEFAULT_MAX_UPLOAD_MB = 100;
export const DEFAULT_MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024;

let cachedBytes: number | null = null;
let inflight: Promise<number> | null = null;

export function applyUploadLimitFetchResult(
  result: { ok: true; bytes: unknown } | { ok: false },
): { cache: number | null; value: number } {
  if (!result.ok) {
    return { cache: null, value: DEFAULT_MAX_UPLOAD_BYTES };
  }
  const bytes = Number(result.bytes);
  const value =
    Number.isFinite(bytes) && bytes > 0 ? bytes : DEFAULT_MAX_UPLOAD_BYTES;
  return { cache: value, value };
}

async function fetchMaxUploadBytes(): Promise<number> {
  if (cachedBytes != null) return cachedBytes;
  if (!inflight) {
    inflight = octopSettingsApi
      .upload()
      .then((settings) => {
        const next = applyUploadLimitFetchResult({
          ok: true,
          bytes: settings.max_upload_bytes,
        });
        cachedBytes = next.cache;
        return next.value;
      })
      .catch(() => {
        const next = applyUploadLimitFetchResult({ ok: false });
        cachedBytes = next.cache;
        return next.value;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Upload size limit from config.json `max_upload_mb` (via GET /api/settings/upload). */
export function useServerUploadLimit(): {
  maxUploadBytes: number;
  maxUploadMb: number;
} {
  const [maxUploadBytes, setMaxUploadBytes] = useState(
    cachedBytes ?? DEFAULT_MAX_UPLOAD_BYTES,
  );

  useEffect(() => {
    void fetchMaxUploadBytes().then(setMaxUploadBytes);
  }, []);

  return {
    maxUploadBytes,
    maxUploadMb: Math.max(1, Math.round(maxUploadBytes / (1024 * 1024))),
  };
}
