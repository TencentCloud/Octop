import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound, Users } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import SettingsTabBar from "../../Settings/shared/SettingsTabBar";
import UsersListPanel from "./UsersListPanel";
import SsoPanel from "./SsoPanel";

type TabKey = "local" | "sso";

const TABS: { key: TabKey; labelKey: string; icon: ReactNode }[] = [
  {
    key: "local",
    labelKey: "adminUsers.tabLocal",
    icon: <Users size={15} />,
  },
  {
    key: "sso",
    labelKey: "adminUsers.tabSso",
    icon: <KeyRound size={15} />,
  },
];

function parseTab(raw: string | null): TabKey {
  if (raw === "sso") return "sso";
  return "local";
}

export default function AdminUsersPage() {
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
    if (key === "local") {
      searchParams.delete("tab");
      setSearchParams(searchParams, { replace: true });
    } else {
      setSearchParams({ tab: key }, { replace: true });
    }
  };

  return (
    <PageShell.Tabbed
      title={t("pageShell.adminUsers.title")}
      subtitle={t("pageShell.adminUsers.subtitle")}
      tabBar={
        <SettingsTabBar
          tabs={TABS}
          activeKey={activeTab}
          onChange={selectTab}
        />
      }
    >
      {activeTab === "local" ? <UsersListPanel /> : <SsoPanel />}
    </PageShell.Tabbed>
  );
}
