import { useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  KeyRound,
  MessageCircle,
  Building2,
  Bell,
  Users,
  type LucideIcon,
} from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import TabBar, { type TabBarItem } from "../../../components/TabLabel/TabBar";
import { TabPanelHeader } from "../../Settings/AdvancedSettings/TabPanelHeader";
import UsersListPanel from "./UsersListPanel";
import SsoPanel from "./SsoPanel";
import OauthProviderCard from "./OauthProviderCard";
import { OAUTH_APP_PROVIDERS, type OauthAppKind } from "./oauthProviders";
import ForbiddenPage from "../../../components/ForbiddenPage";
import { useGatedSearchTabs } from "../../../hooks/useGatedSearchTabs";
import { USERS_TAB_PERMISSIONS } from "../../../utils/permissions";
import styles from "./index.module.less";

type TabKey = "local" | OauthAppKind | "oidc";

const OAUTH_TAB_ICONS: Record<OauthAppKind, LucideIcon> = {
  feishu: MessageCircle,
  wecom: Building2,
  dingtalk: Bell,
};

const TABS: TabBarItem<TabKey>[] = [
  { key: "local", labelKey: "adminUsers.tabLocal", icon: Users },
  { key: "oidc", labelKey: "adminUsers.tabOidc", icon: KeyRound },
  { key: "feishu", labelKey: "adminUsers.tabFeishu", icon: MessageCircle },
  { key: "wecom", labelKey: "adminUsers.tabWecom", icon: Building2 },
  { key: "dingtalk", labelKey: "adminUsers.tabDingtalk", icon: Bell },
];

function parseTab(raw: string | null): TabKey {
  if (
    raw === "feishu" ||
    raw === "wecom" ||
    raw === "dingtalk" ||
    raw === "oidc"
  ) {
    return raw;
  }
  // Legacy bookmark: combined SSO tab → OIDC.
  if (raw === "sso") return "oidc";
  return "local";
}

function OauthTabPanel({ kind }: { kind: OauthAppKind }) {
  const { t } = useTranslation();
  const provider = useMemo(
    () => OAUTH_APP_PROVIDERS.find((item) => item.kind === kind),
    [kind],
  );
  if (!provider) return null;
  const Icon = OAUTH_TAB_ICONS[kind];

  return (
    <div className={styles.ssoPanel}>
      <TabPanelHeader
        icon={<Icon size={22} />}
        title={t(provider.titleKey)}
        description={t(provider.descKey)}
      />
      <OauthProviderCard provider={provider} standalone />
    </div>
  );
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

  let body: ReactNode = <UsersListPanel />;
  if (activeTab === "oidc") {
    body = (
      <div className={styles.ssoPanel}>
        <TabPanelHeader
          icon={<KeyRound size={22} />}
          title={t("adminSso.oidcTitle")}
          description={t("adminSso.oidcDesc")}
        />
        <SsoPanel />
      </div>
    );
  } else if (
    activeTab === "feishu" ||
    activeTab === "wecom" ||
    activeTab === "dingtalk"
  ) {
    body = <OauthTabPanel kind={activeTab} />;
  }

  return (
    <PageShell.Tabbed
      title={t("pageShell.adminUsers.title")}
      subtitle={t("pageShell.adminUsers.subtitle")}
      tabBar={
        <TabBar tabs={allowedTabs} activeKey={activeTab} onChange={selectTab} />
      }
    >
      {body}
    </PageShell.Tabbed>
  );
}
