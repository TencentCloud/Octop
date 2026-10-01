import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import BridgeSettingsPanel from "../AdvancedSettings/BridgeSettings";

/** User-scoped remote bridge settings (Settings → under Knowledge Bases). */
export default function BridgePage() {
  const { t } = useTranslation();
  return (
    <PageShell
      title={t("pageShell.bridge.title")}
      subtitle={t("pageShell.bridge.subtitle")}
    >
      <BridgeSettingsPanel asPage />
    </PageShell>
  );
}
