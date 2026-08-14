import type { ReactNode } from "react";
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
import ForbiddenPage from "../../../components/ForbiddenPage";
import { useGatedSearchTabs } from "../../../hooks/useGatedSearchTabs";
import { ADVANCED_TAB_PERMISSIONS } from "../../../utils/permissions";

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
  const { allowedTabs, activeTab, forbidden, selectTab } = useGatedSearchTabs({
    tabs: TABS,
    tabPermissions: ADVANCED_TAB_PERMISSIONS,
    parseTab,
    querylessKey: "env-vars",
  });

  if (forbidden) return <ForbiddenPage />;

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
          tabs={allowedTabs}
          activeKey={activeTab}
          onChange={selectTab}
        />
      }
    >
      <div className={tabStyles.panel}>{renderTab()}</div>
    </PageShell.Tabbed>
  );
}
