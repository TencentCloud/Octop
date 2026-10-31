import { useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Group, IdCard, KeyRound, Network, Users } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import TabBar, { type TabBarItem } from "../../../components/TabLabel/TabBar";
import { TAB_ICON_SIZE } from "../../../components/TabLabel";
import { TabPanelHeader } from "../../Settings/AdvancedSettings/TabPanelHeader";
import RolesPanel from "./RolesPanel";
import GroupsPanel from "./GroupsPanel";
import UsersListPanel from "./UsersListPanel";
import SsoPanel from "./SsoPanel";
import LdapPanel from "./LdapPanel";
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

type TabKey = "local" | "roles" | "groups" | OauthAppKind | "oidc" | "ldap";

// external（外部系统免登）无品牌图标，用 lucide KeyRound 兜底
const OAUTH_BRAND_ICONS: Record<Exclude<OauthAppKind, "external">, string> = {
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
  { key: "roles", labelKey: "adminUsers.tabRoles", icon: IdCard },
  { key: "groups", labelKey: "adminUsers.tabGroups", icon: Group },
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
  {
    key: "ldap",
    labelKey: "adminUsers.tabLdap",
    icon: Network,
  },
  {
    key: "external",
    labelKey: "adminUsers.tabExternal",
    icon: KeyRound,
    // 直链与 F12 检索用的可见中文；i18n 未命中时仍显示
    fallback: "外部系统登录",
  },
];

function parseTab(raw: string | null): TabKey {
  if (raw === "roles") return "roles";
  if (raw === "groups") return "groups";
  if (
    raw === "feishu" ||
    raw === "wecom" ||
    raw === "dingtalk" ||
    raw === "oidc" ||
    raw === "ldap" ||
    raw === "external"
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
        icon={
          kind === "external" ? (
            <KeyRound size={22} />
          ) : (
            <BrandTabIcon src={OAUTH_BRAND_ICONS[kind]} size={22} />
          )
        }
        title={
          kind === "external"
            ? t(provider.titleKey, "外部系统登录")
            : t(provider.titleKey)
        }
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
  if (activeTab === "roles") {
    body = <RolesPanel />;
  } else if (activeTab === "groups") {
    body = <GroupsPanel />;
  } else if (activeTab === "oidc") {
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
  } else if (activeTab === "ldap") {
    body = (
      <div className={styles.ssoPanel}>
        <TabPanelHeader
          icon={<Network size={22} />}
          title={t("adminSso.ldapTitle")}
          description={t("adminSso.ldapDesc")}
        />
        <LdapPanel />
      </div>
    );
  } else if (
    activeTab === "feishu" ||
    activeTab === "wecom" ||
    activeTab === "dingtalk" ||
    activeTab === "external"
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
