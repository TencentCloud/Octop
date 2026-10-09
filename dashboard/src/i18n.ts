import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { getApiUrl } from "./api/config";
import { i18nApi } from "./api/modules/i18n";
import {
  normalizeUiLocale,
  resolveInitialLocale,
  syncDocumentLang,
  type UiLocale,
} from "./utils/localePrefs";

export type { UiLocale } from "./utils/localePrefs";

async function loadLocaleBundle(locale: UiLocale) {
  if (locale === "zh") {
    return (await import("./locales/zh.json")).default;
  }
  if (locale === "ja") {
    return (await import("./locales/ja.json")).default;
  }
  return (await import("./locales/en.json")).default;
}

export async function ensureLocaleBundle(locale: UiLocale): Promise<void> {
  if (!i18n.hasResourceBundle(locale, "translation")) {
    const bundle = await loadLocaleBundle(locale);
    i18n.addResourceBundle(locale, "translation", bundle, true, true);
  }
}

/** Raw fetch — avoids importing ``request.ts`` (circular via this module). */
async function isSetupRequired(): Promise<boolean> {
  try {
    const res = await fetch(getApiUrl("/setup/status"));
    if (!res.ok) return true;
    const body = (await res.json()) as { setup_required?: boolean };
    return body.setup_required === true;
  } catch {
    return true;
  }
}

async function hydrateToolLabels(lng: string) {
  const locale = normalizeUiLocale(lng);
  try {
    const { labels } = await i18nApi.getToolLabels();
    // Server only ships zh/en labels; for ja keep bundled translations and
    // use the server's (English) labels only to fill missing keys.
    i18n.addResourceBundle(
      locale,
      "translation",
      { tools: labels },
      true,
      locale !== "ja",
    );
  } catch {
    // bundled locale JSON remains the fallback
  }
}

async function hydrateSkillLabels(lng: string) {
  const locale = normalizeUiLocale(lng);
  try {
    const { labels } = await i18nApi.getSkillLabels();
    // Server only ships zh/en labels; for ja keep bundled translations and
    // use the server's (English) labels only to fill missing keys.
    i18n.addResourceBundle(
      locale,
      "translation",
      { skills: labels },
      true,
      locale !== "ja",
    );
  } catch {
    // bundled locale JSON remains the fallback
  }
}

async function hydrateServerLabels(lng: string) {
  if (await isSetupRequired()) return;
  await Promise.all([hydrateToolLabels(lng), hydrateSkillLabels(lng)]);
}

/** Pull tool/skill labels from the backend (e.g. after setup or login). */
export function refreshServerLabels(lng?: string): Promise<void> {
  return hydrateServerLabels(lng ?? i18n.language);
}

let initPromise: Promise<void> | null = null;

export function initI18n(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      const initial = resolveInitialLocale();
      const fallback: UiLocale = initial === "en" ? "zh" : "en";
      const primaryBundle = await loadLocaleBundle(initial);

      await i18n.use(initReactI18next).init({
        resources: {
          [initial]: { translation: primaryBundle },
        },
        lng: initial,
        fallbackLng: fallback,
        supportedLngs: ["zh", "en", "ja"],
        nonExplicitSupportedLngs: true,
        interpolation: {
          escapeValue: false,
        },
      });

      syncDocumentLang(initial);

      const prefetchFallback = () => {
        void ensureLocaleBundle(fallback);
      };
      if (typeof requestIdleCallback !== "undefined") {
        requestIdleCallback(prefetchFallback);
      } else {
        setTimeout(prefetchFallback, 2000);
      }

      i18n.on("languageChanged", (lng) => {
        const locale: UiLocale = normalizeUiLocale(lng);
        syncDocumentLang(locale);
        void ensureLocaleBundle(locale).then(() => hydrateServerLabels(lng));
      });

      void hydrateServerLabels(i18n.language);
    })();
  }
  return initPromise;
}

export default i18n;
