import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Tabs } from "antd";
import { Puzzle, Store } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import TabLabel from "../../../components/TabLabel";
import { InstalledPluginsPanel } from "./InstalledPluginsPanel";
import { PluginMarketPanel } from "./PluginMarketPanel";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { PLUGIN_TAB_PERMISSIONS, userCan } from "../../../utils/permissions";

type TabKey = "installed" | "market";

function parseTab(raw: string | null): TabKey {
  if (raw === "market") return "market";
  // Legacy ?tab=agent-tools redirects to installed (tools live in plugin detail).
  return "installed";
}

export default function AdminPluginsPage() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabKey>(() =>
    parseTab(searchParams.get("tab")),
  );
  const visibleTabs = useMemo(
    () =>
      (["installed", "market"] as const).filter((key) =>
        userCan(user, PLUGIN_TAB_PERMISSIONS[key]),
      ),
    [user],
  );
  const resolvedTab = visibleTabs.includes(activeTab)
    ? activeTab
    : visibleTabs[0] ?? "installed";

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
        activeKey={resolvedTab}
        onChange={selectTab}
        items={[
          ...(visibleTabs.includes("installed")
            ? [
                {
                  key: "installed",
                  label: (
                    <TabLabel icon={Puzzle}>
                      {t("plugins.tabInstalled")}
                    </TabLabel>
                  ),
                  children: <InstalledPluginsPanel />,
                },
              ]
            : []),
          ...(visibleTabs.includes("market")
            ? [
                {
                  key: "market",
                  label: (
                    <TabLabel icon={Store}>{t("plugins.tabMarket")}</TabLabel>
                  ),
                  children: <PluginMarketPanel />,
                },
              ]
            : []),
        ]}
      />
    </PageShell.FillTabs>
  );
}
