import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import EnvironmentsPage from "../Environments";
import SearchConfigPage from "../SearchConfig";
import { VoiceSettingsPanel } from "../Voice";
import { ObservabilitySettingsPanel } from "../Observability";
import BackupRestorePanel from "../BackupRestore";
import { HttpsSettingsPanel } from "../HttpsSettings";
import UpdateConfig from "./UpdateConfig";
import PageShell from "../../../layouts/PageShell";
import styles from "./index.module.less";
import tabStyles from "./tabContent.module.less";

type TabKey =
  | "env-vars"
  | "search"
  | "voice"
  | "observability"
  | "backup"
  | "https"
  | "updates";

const TABS: { key: TabKey; labelKey: string }[] = [
  { key: "env-vars", labelKey: "nav.environments" },
  { key: "search", labelKey: "nav.search" },
  { key: "voice", labelKey: "nav.voice" },
  { key: "observability", labelKey: "nav.observability" },
  { key: "backup", labelKey: "nav.backupRestore" },
  { key: "https", labelKey: "nav.https" },
  { key: "updates", labelKey: "nav.checkUpdates" },
];

function parseTab(raw: string | null): TabKey {
  if (
    raw === "search" ||
    raw === "voice" ||
    raw === "observability" ||
    raw === "backup" ||
    raw === "https" ||
    raw === "updates"
  ) {
    return raw;
  }
  return "env-vars";
}

export default function AdvancedSettingsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabKey>(() =>
    parseTab(searchParams.get("tab")),
  );

  useEffect(() => {
    setActiveTab(parseTab(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = (key: TabKey) => {
    setActiveTab(key);
    if (key === "env-vars") {
      searchParams.delete("tab");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ tab: key }, { replace: true });
    }
  };

  const renderTab = () => {
    switch (activeTab) {
      case "env-vars":
        return <EnvironmentsPage />;
      case "search":
        return <SearchConfigPage />;
      case "voice":
        return <VoiceSettingsPanel />;
      case "observability":
        return <ObservabilitySettingsPanel />;
      case "backup":
        return <BackupRestorePanel />;
      case "https":
        return <HttpsSettingsPanel />;
      case "updates":
        return <UpdateConfig />;
    }
  };

  return (
    <PageShell
      title={t("pageShell.adminAdvanced.title")}
      subtitle={t("pageShell.adminAdvanced.subtitle")}
    >
      <div className={styles.tabBar} role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`${styles.tab} ${
              activeTab === tab.key ? styles.active : ""
            }`}
            onClick={() => selectTab(tab.key)}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      <div className={styles.tabContent} role="tabpanel">
        <div className={styles.tabInner}>
          <div className={tabStyles.panel}>{renderTab()}</div>
        </div>
      </div>
    </PageShell>
  );
}
