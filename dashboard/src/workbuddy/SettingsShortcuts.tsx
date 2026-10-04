import { useTranslation } from "react-i18next";
export default function SettingsShortcuts() {
  const { t } = useTranslation();
  return (
    <div className="wb-settings-shortcuts">
      <p>{t("workbuddy.settings.shortcutSend")}</p>
      <p>{t("workbuddy.settings.shortcutSelect")}</p>
    </div>
  );
}
