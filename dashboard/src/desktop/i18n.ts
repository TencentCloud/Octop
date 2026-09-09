import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import {
  resolveInitialLocale,
  storeUiLocale,
  syncDocumentLang,
  type UiLocale,
} from "../utils/localePrefs";

async function loadLocaleBundle(locale: UiLocale) {
  if (locale === "zh") {
    return (await import("../locales/zh.json")).default;
  }
  return (await import("../locales/en.json")).default;
}

let initPromise: Promise<void> | null = null;

/** Shell-only i18n: locale JSON, no dashboard API hydration. */
export function initDesktopI18n(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      const initial = resolveInitialLocale();
      const fallback: UiLocale = initial === "zh" ? "en" : "zh";
      const primaryBundle = await loadLocaleBundle(initial);

      await i18n.use(initReactI18next).init({
        resources: {
          [initial]: { translation: primaryBundle },
        },
        lng: initial,
        fallbackLng: fallback,
        supportedLngs: ["zh", "en"],
        nonExplicitSupportedLngs: true,
        interpolation: {
          escapeValue: false,
        },
      });

      syncDocumentLang(initial);

      i18n.on("languageChanged", (lng) => {
        const locale: UiLocale = lng.startsWith("zh") ? "zh" : "en";
        storeUiLocale(locale);
        syncDocumentLang(locale);
        void loadLocaleBundle(locale).then((bundle) => {
          if (!i18n.hasResourceBundle(locale, "translation")) {
            i18n.addResourceBundle(locale, "translation", bundle, true, true);
          }
        });
      });
    })();
  }
  return initPromise;
}

export async function applyDesktopLocale(locale: UiLocale): Promise<void> {
  if (!i18n.hasResourceBundle(locale, "translation")) {
    const bundle = await loadLocaleBundle(locale);
    i18n.addResourceBundle(locale, "translation", bundle, true, true);
  }
  await i18n.changeLanguage(locale);
}

export default i18n;
