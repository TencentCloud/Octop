import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card } from "antd";
import PageShell from "../../../layouts/PageShell";
import advStyles from "../../Settings/AdvancedSettings/index.module.less";
import { AgentToolsPanel } from "./AgentToolsPanel";
import { InstalledPluginsPanel } from "./InstalledPluginsPanel";

type TabKey = "installed" | "agent-tools";

const TABS: { key: TabKey; labelKey: string }[] = [
  { key: "installed", labelKey: "plugins.tabInstalled" },
  { key: "agent-tools", labelKey: "plugins.tabAgentTools" },
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
        <div className={advStyles.tabBar} role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.key}
              className={`${advStyles.tab} ${
                activeTab === tab.key ? advStyles.active : ""
              }`}
              onClick={() => selectTab(tab.key)}
            >
              {t(tab.labelKey)}
            </button>
          ))}
        </div>
      }
    >
      <Card>
        {activeTab === "installed" ? (
          <InstalledPluginsPanel />
        ) : (
          <AgentToolsPanel />
        )}
      </Card>
    </PageShell.Tabbed>
  );
}
