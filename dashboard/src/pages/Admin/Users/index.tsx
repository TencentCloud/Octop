import { useTranslation } from "react-i18next";
import { KeyRound, Users } from "lucide-react";
import type { ReactNode } from "react";
import PageShell from "../../../layouts/PageShell";
import SettingsTabBar from "../../Settings/shared/SettingsTabBar";
import UsersListPanel from "./UsersListPanel";
import SsoPanel from "./SsoPanel";
import ForbiddenPage from "../../../components/ForbiddenPage";
import { useGatedSearchTabs } from "../../../hooks/useGatedSearchTabs";
import { USERS_TAB_PERMISSIONS } from "../../../utils/permissions";

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
  const { allowedTabs, activeTab, forbidden, selectTab } = useGatedSearchTabs({
    tabs: TABS,
    tabPermissions: USERS_TAB_PERMISSIONS,
    parseTab,
    querylessKey: "local",
  });

  if (forbidden) return <ForbiddenPage />;

  return (
    <PageShell.Tabbed
      title={t("pageShell.adminUsers.title")}
      subtitle={t("pageShell.adminUsers.subtitle")}
      tabBar={
        <SettingsTabBar
          tabs={allowedTabs}
          activeKey={activeTab}
          onChange={selectTab}
        />
      }
    >
      {activeTab === "local" ? <UsersListPanel /> : <SsoPanel />}
    </PageShell.Tabbed>
  );
}
