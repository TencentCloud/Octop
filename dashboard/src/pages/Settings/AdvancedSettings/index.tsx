import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useSearchParams } from "react-router-dom";
import { Archive, Lock, RefreshCw, Variable, Activity } from "lucide-react";
import EnvironmentsPage from "../Environments";
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

type TabKey = "env-vars" | "observability" | "backup" | "https" | "updates";

const TABS: { key: TabKey; labelKey: string; icon: ReactNode }[] = [
  {
    key: "env-vars",
    labelKey: "nav.environments",
    icon: <Variable size={15} />,
  },
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
  const [searchParams] = useSearchParams();
  const { allowedTabs, activeTab, forbidden, selectTab } = useGatedSearchTabs({
    tabs: TABS,
    tabPermissions: ADVANCED_TAB_PERMISSIONS,
    parseTab,
    querylessKey: "env-vars",
  });

  const moved = searchParams.get("tab");
  if (moved === "voice" || moved === "search") {
    return <Navigate to={`/admin/models?tab=${moved}`} replace />;
  }

  if (forbidden) return <ForbiddenPage />;

  const renderTab = () => {
    switch (activeTab) {
      case "env-vars":
        return <EnvironmentsPage />;
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
