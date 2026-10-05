import type { TFunction } from "i18next";

import { apiErrorMessage, parseApiError } from "../../../utils/apiError";

export interface StorageProbeResult {
  ok?: boolean;
  message?: string;
  message_key?: string;
}

export function storageProbeMessage(
  result: StorageProbeResult,
  t: TFunction,
  fallbackKey: string,
): string {
  if (result.message_key) {
    return t(`storage.${result.message_key}`, {
      defaultValue: result.message || t(fallbackKey),
      detail: result.message || "",
    });
  }
  return result.message || t(fallbackKey);
}

export function storageBrowseError(error: unknown, t: TFunction): string {
  const parsed = parseApiError(error);
  const key = parsed?.details?.message_key;
  if (typeof key === "string" && key) {
    const reason =
      typeof parsed?.details?.reason === "string"
        ? parsed.details.reason
        : parsed.message || "";
    return storageProbeMessage(
      { message_key: key, message: reason },
      t,
      "storage.browseFailed",
    );
  }
  return apiErrorMessage(error, t("storage.browseFailed"), t);
}
