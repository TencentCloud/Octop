import { useTranslation } from "react-i18next";
import PwaInstallPrompt from "../components/PwaInstallPrompt";
import { DEFERRED_FEATURES } from "./capabilities";
export default function SettingsAbout() {
  const { t } = useTranslation();
  return (
    <div className="wb-settings-about">
      <h3>Octop</h3>
      <p>{t("workbuddy.settings.aboutDescription")}</p>
      <PwaInstallPrompt />
      <a href="https://octop.cloud" target="_blank" rel="noopener noreferrer">
        {t("account.helpFeedback")}
      </a>
      <h3>{t("workbuddy.settings.extensions")}</h3>
      {DEFERRED_FEATURES.filter(
        (item) => !["projects", "space"].includes(item.id),
      ).map((item) => (
        <p key={item.id}>
          {t(item.labelKey)} · {t("workbuddy.notConnected")}
        </p>
      ))}
    </div>
  );
}
