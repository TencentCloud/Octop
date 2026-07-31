import type { TFunction } from "i18next";
import { apiErrorMessage } from "./apiError";

import { message } from "@/utils/antdMessage";

/** Show an API error toast with optional i18n fallback and code translation. */
export function showApiError(
  error: unknown,
  fallback: string,
  t?: TFunction,
): void {
  message.error(apiErrorMessage(error, fallback, t));
}
