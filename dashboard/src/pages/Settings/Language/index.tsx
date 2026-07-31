import { useTranslation } from "react-i18next";
import { Radio, Space } from "antd";
import { message } from "@/utils/antdMessage";

import { preferencesApi } from "../../../api/modules/preferences";
import { applyUserLocale } from "../../../utils/locale";

const languages = [
  { value: "en", label: "English" },
  { value: "zh", label: "简体中文" },
];

export default function LanguagePage() {
  const { t, i18n } = useTranslation();

  const handleChange = async (lang: string) => {
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
    <div style={{ padding: "32px 40px", maxWidth: 600 }}>
      <h2
        style={{
          fontSize: 20,
          fontWeight: 600,
          color: "var(--fn-text-primary)",
          marginBottom: 8,
        }}
      >
        {t("language.title")}
      </h2>
      <p
        style={{
          fontSize: 14,
          color: "var(--fn-text-tertiary)",
          marginBottom: 24,
        }}
      >
        {t("language.description")}
      </p>

      <Radio.Group
        value={i18n.language?.startsWith("zh") ? "zh" : "en"}
        onChange={(e) => void handleChange(e.target.value)}
      >
        <Space direction="vertical" size={12}>
          {languages.map((lang) => (
            <Radio key={lang.value} value={lang.value}>
              {lang.label}
            </Radio>
          ))}
        </Space>
      </Radio.Group>
    </div>
  );
}
