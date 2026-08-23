import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Tabs } from "antd";
import PageShell from "../../../layouts/PageShell";
import { InstalledPluginsPanel } from "./InstalledPluginsPanel";
import { PluginMarketPanel } from "./PluginMarketPanel";

type TabKey = "installed" | "market";

function parseTab(raw: string | null): TabKey {
  if (raw === "market") return "market";
  // Legacy ?tab=agent-tools redirects to installed (tools live in plugin detail).
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

  const selectTab = (key: string) => {
    const next = parseTab(key);
    setActiveTab(next);
    if (next === "installed") {
      searchParams.delete("tab");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ tab: next }, { replace: true });
    }
  };

  return (
    <PageShell.FillTabs
      title={t("pageShell.adminPlugins.title")}
      subtitle={t("pageShell.adminPlugins.subtitle")}
    >
      <Tabs
        activeKey={activeTab}
        onChange={selectTab}
        items={[
          {
            key: "installed",
            label: t("plugins.tabInstalled"),
            children: <InstalledPluginsPanel />,
          },
          {
            key: "market",
            label: t("plugins.tabMarket"),
            children: <PluginMarketPanel />,
          },
        ]}
      />
    </PageShell.FillTabs>
  );
}
