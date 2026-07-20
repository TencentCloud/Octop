import type { UiLocale } from "./locale";

export interface LocalizedText {
  zh?: string;
  en?: string;
}

/** Pick the best string for the active UI locale, with cross-locale fallback. */
export function pickLocale(
  node: LocalizedText | undefined,
  locale: UiLocale,
  options?: { crossFallback?: boolean },
): string {
  if (!node) return "";
  const crossFallback = options?.crossFallback !== false;
  if (locale === "zh") {
    if (node.zh) return node.zh;
    return crossFallback ? node.en || "" : "";
  }
  if (node.en) return node.en;
  return crossFallback ? node.zh || "" : "";
}
