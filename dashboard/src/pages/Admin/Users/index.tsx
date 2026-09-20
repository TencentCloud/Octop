import { useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Users } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import TabBar, { type TabBarItem } from "../../../components/TabLabel/TabBar";
import { TAB_ICON_SIZE } from "../../../components/TabLabel";
import { TabPanelHeader } from "../../Settings/AdvancedSettings/TabPanelHeader";
import UsersListPanel from "./UsersListPanel";
import SsoPanel from "./SsoPanel";
import OauthProviderCard from "./OauthProviderCard";
import { OAUTH_APP_PROVIDERS, type OauthAppKind } from "./oauthProviders";
import ForbiddenPage from "../../../components/ForbiddenPage";
import { useGatedSearchTabs } from "../../../hooks/useGatedSearchTabs";
import { USERS_TAB_PERMISSIONS } from "../../../utils/permissions";
import feishuIcon from "../../../assets/channels/feishu.svg";
import wecomIcon from "../../../assets/channels/wecom.svg";
import dingtalkIcon from "../../../assets/channels/dingtalk.svg";
import openidIcon from "../../../assets/providers/openid.svg";
import styles from "./index.module.less";

type TabKey = "local" | OauthAppKind | "oidc";

const OAUTH_BRAND_ICONS: Record<OauthAppKind, string> = {
  feishu: feishuIcon,
  wecom: wecomIcon,
  dingtalk: dingtalkIcon,
};

function BrandTabIcon({
  src,
  size = TAB_ICON_SIZE,
}: {
  src: string;
  size?: number;
}) {
  return <img src={src} alt="" width={size} height={size} draggable={false} />;
}

const TABS: TabBarItem<TabKey>[] = [
  { key: "local", labelKey: "adminUsers.tabLocal", icon: Users },
  {
    key: "feishu",
    labelKey: "adminUsers.tabFeishu",
    icon: <BrandTabIcon src={feishuIcon} />,
  },
  {
    key: "wecom",
    labelKey: "adminUsers.tabWecom",
    icon: <BrandTabIcon src={wecomIcon} />,
  },
  {
    key: "dingtalk",
    labelKey: "adminUsers.tabDingtalk",
    icon: <BrandTabIcon src={dingtalkIcon} />,
  },
  {
    key: "oidc",
    labelKey: "adminUsers.tabOidc",
    icon: <BrandTabIcon src={openidIcon} />,
  },
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

  return (
    <div className={styles.ssoPanel}>
      <TabPanelHeader
        icon={<BrandTabIcon src={OAUTH_BRAND_ICONS[kind]} size={22} />}
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
          icon={<BrandTabIcon src={openidIcon} size={22} />}
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
