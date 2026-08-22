import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Monitor, Smartphone } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import { usePathTabs } from "../../../hooks/usePathTabs";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { useServerCapabilities } from "../../../hooks/useServerCapabilities";
import { userCan } from "../../../utils/permissions";
import DesktopPanel from "./DesktopPanel";
import RemoteAndroidPage from "../RemoteAndroid";
import styles from "./index.module.less";

export type RemoteDesktopTab = "desktop" | "phone";

const REMOTE_DESKTOP_TABS = [
  "desktop",
  "phone",
] as const satisfies readonly RemoteDesktopTab[];

const TAB_ICONS = {
  desktop: Monitor,
  phone: Smartphone,
} as const;

export default function RemoteDesktopPage() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const { mobileEnabled } = useServerCapabilities();

  const isAllowed = useCallback(
    (tab: RemoteDesktopTab) => {
      if (tab === "desktop") return userCan(user, "desktop");
      return mobileEnabled && userCan(user, "mobile");
    },
    [user, mobileEnabled],
  );

  const defaultTab: RemoteDesktopTab = userCan(user, "desktop")
    ? "desktop"
    : "phone";

  const { activeTab, handleTabChange, isMounted } = usePathTabs({
    basePath: "/remote-desktop",
    tabs: REMOTE_DESKTOP_TABS,
    storageKey: "octop:remote-desktop:tab",
    defaultTab,
    isAllowed,
  });

  const pathTabs = useMemo(
    () => ({
      value: activeTab,
      onChange: handleTabChange,
      options: REMOTE_DESKTOP_TABS.filter((value) => isAllowed(value)).map(
        (value) => {
          const Icon = TAB_ICONS[value];
          return {
            value,
            label: t(`remoteDesktopHub.tabs.${value}`),
            icon: <Icon size={14} strokeWidth={2} />,
          };
        },
      ),
    }),
    [activeTab, handleTabChange, isAllowed, t],
  );

  const desktopVisible = activeTab === "desktop";
  const phoneVisible = activeTab === "phone";
  const pageTitle = `${t("remoteDesktopHub.title")} / ${t(
    `remoteDesktopHub.tabs.${activeTab}`,
  )}`;

  return (
    <PageShell
      title={pageTitle}
      subtitle={t("remoteDesktopHub.description")}
      fill
      pathTabs={pathTabs}
    >
      <div className={styles.panels}>
        {isMounted("desktop") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "desktop" ? "flex" : "none" }}
            aria-hidden={activeTab !== "desktop"}
          >
            <DesktopPanel embedded isVisible={desktopVisible} />
          </div>
        )}
        {isMounted("phone") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "phone" ? "flex" : "none" }}
            aria-hidden={activeTab !== "phone"}
          >
            <RemoteAndroidPage embedded isVisible={phoneVisible} />
          </div>
        )}
      </div>
    </PageShell>
  );
}
