import { useState, useEffect, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Archive,
  Lock,
  Mic2,
  RefreshCw,
  Search,
  Variable,
  Activity,
} from "lucide-react";
import EnvironmentsPage from "../Environments";
import SearchConfigPage from "../SearchConfig";
import { VoiceSettingsPanel } from "../Voice";
import { ObservabilitySettingsPanel } from "../Observability";
import BackupRestorePanel from "../BackupRestore";
import { HttpsSettingsPanel } from "../HttpsSettings";
import UpdateConfig from "./UpdateConfig";
import PageShell from "../../../layouts/PageShell";
import SettingsTabBar from "../shared/SettingsTabBar";
import tabStyles from "./tabContent.module.less";

type TabKey =
  | "env-vars"
  | "search"
  | "voice"
  | "observability"
  | "backup"
  | "https"
  | "updates";

const TABS: { key: TabKey; labelKey: string; icon: ReactNode }[] = [
  {
    key: "env-vars",
    labelKey: "nav.environments",
    icon: <Variable size={15} />,
  },
  { key: "search", labelKey: "nav.search", icon: <Search size={15} /> },
  { key: "voice", labelKey: "nav.voice", icon: <Mic2 size={15} /> },
  {
    key: "observability",
    labelKey: "nav.observability",
    icon: <Activity size={15} />,
  },
  { key: "backup", labelKey: "nav.backupRestore", icon: <Archive size={15} /> },
  { key: "https", labelKey: "nav.https", icon: <Lock size={15} /> },
  {
    key: "updates",
    labelKey: "nav.checkUpdates",
    icon: <RefreshCw size={15} />,
  },
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
    <PageShell.Tabbed
      title={t("pageShell.adminAdvanced.title")}
      subtitle={t("pageShell.adminAdvanced.subtitle")}
      tabBar={
        <SettingsTabBar
          tabs={TABS}
          activeKey={activeTab}
          onChange={selectTab}
        />
      }
    >
      <div className={tabStyles.panel}>{renderTab()}</div>
    </PageShell.Tabbed>
  );
}
