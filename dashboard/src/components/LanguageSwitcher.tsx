import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import { preferencesApi } from "../api/modules/preferences";
import { applyUserLocale, normalizeUiLocale } from "../utils/locale";

const LANGUAGES = [
  { key: "zh", label: "中", title: "简体中文" },
  { key: "en", label: "EN", title: "English" },
  { key: "ko", label: "한", title: "한국어" },
];

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const currentLanguage = normalizeUiLocale(i18n.language);

  const changeLanguage = async (lang: string) => {
    try {
      const prefs = await preferencesApi.setLocale(lang);
      await applyUserLocale(prefs.locale);
    } catch {
      message.error(
        t("language.saveFailed", "Failed to save language preference"),
      );
    }
  };

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 2,
        padding: 3,
        borderRadius: "var(--fn-radius-full, 999px)",
        background: "var(--fn-bg-tertiary)",
      }}
    >
      {LANGUAGES.map(({ key, label, title }) => {
        const active = currentLanguage === key;
        return (
          <Tooltip key={key} title={title} mouseEnterDelay={0.4}>
            <button
              onClick={() => void changeLanguage(key)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 32,
                height: 32,
                border: "none",
                borderRadius: "var(--fn-radius-full, 999px)",
                background: active ? "var(--fn-bg-elevated)" : "transparent",
                color: active
                  ? "var(--fn-text-primary)"
                  : "var(--fn-text-secondary)",
                boxShadow: active ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                cursor: "pointer",
                transition: "all 0.2s ease",
                fontSize: 13,
                fontWeight: active ? 600 : 400,
              }}
            >
              {label}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
