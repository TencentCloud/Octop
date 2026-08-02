import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Package, Wrench } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import SettingsTabBar from "../../Settings/shared/SettingsTabBar";
import { AgentToolsPanel } from "./AgentToolsPanel";
import { InstalledPluginsPanel } from "./InstalledPluginsPanel";

type TabKey = "installed" | "agent-tools";

const TABS: { key: TabKey; labelKey: string; icon: ReactNode }[] = [
  {
    key: "installed",
    labelKey: "plugins.tabInstalled",
    icon: <Package size={15} />,
  },
  {
    key: "agent-tools",
    labelKey: "plugins.tabAgentTools",
    icon: <Wrench size={15} />,
  },
];

function parseTab(raw: string | null): TabKey {
  if (raw === "agent-tools") return "agent-tools";
  return "installed";
}

export default function AdminPluginsPage() {
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
    if (key === "installed") {
      searchParams.delete("tab");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ tab: key }, { replace: true });
    }
  };

  return (
    <PageShell.Tabbed
      title={t("pageShell.adminPlugins.title")}
      subtitle={t("pageShell.adminPlugins.subtitle")}
      tabBar={
        <SettingsTabBar
          tabs={TABS}
          activeKey={activeTab}
          onChange={selectTab}
        />
      }
    >
      {activeTab === "installed" ? (
        <InstalledPluginsPanel />
      ) : (
        <AgentToolsPanel />
      )}
    </PageShell.Tabbed>
  );
}
