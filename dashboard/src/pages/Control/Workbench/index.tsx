import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Server, TerminalSquare } from "lucide-react";
import PageShell from "../../../layouts/PageShell";
import { usePathTabs } from "../../../hooks/usePathTabs";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { userCan, userCanAny } from "../../../utils/permissions";
import TerminalPage from "../Terminal";
import RemoteBrowserPage from "../RemoteBrowser";
import CloudHostsPage from "../CloudHosts";
import styles from "./index.module.less";

export type WorkbenchTab = "terminal" | "browser" | "cloud";

const WORKBENCH_TABS = [
  "browser",
  "terminal",
  "cloud",
] as const satisfies readonly WorkbenchTab[];

const TAB_ICONS = {
  browser: Globe,
  terminal: TerminalSquare,
  cloud: Server,
} as const;

interface WorkbenchPageProps {
  /** True when the workbench keep-alive surface is currently shown. */
  isVisible?: boolean;
}

export default function WorkbenchPage({
  isVisible = true,
}: WorkbenchPageProps) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const isAllowed = useCallback(
    (tab: WorkbenchTab) =>
      tab === "cloud"
        ? userCanAny(user, ["browser", "terminal"])
        : userCan(user, tab),
    [user],
  );
  const defaultTab: WorkbenchTab = userCan(user, "browser")
    ? "browser"
    : "terminal";

  const { activeTab, handleTabChange, isMounted } = usePathTabs({
    basePath: "/workbench",
    tabs: WORKBENCH_TABS,
    storageKey: "octop:workbench:tab",
    defaultTab,
    isAllowed,
  });

  const pathTabs = useMemo(
    () => ({
      value: activeTab,
      onChange: handleTabChange,
      options: WORKBENCH_TABS.filter((value) => isAllowed(value)).map(
        (value) => {
          const Icon = TAB_ICONS[value];
          return {
            value,
            label: t(`workbench.tabs.${value}`),
            icon: <Icon size={14} strokeWidth={1.75} />,
          };
        },
      ),
    }),
    [activeTab, handleTabChange, isAllowed, t],
  );

  const browserVisible = isVisible && activeTab === "browser";
  const terminalVisible = isVisible && activeTab === "terminal";
  const pageTitle = `${t("workbench.title")} / ${t(
    `workbench.tabs.${activeTab}`,
  )}`;

  return (
    <PageShell
      title={pageTitle}
      subtitle={t("workbench.description")}
      fill
      pathTabs={pathTabs}
    >
      <div className={styles.panels}>
        {isMounted("browser") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "browser" ? "flex" : "none" }}
            aria-hidden={activeTab !== "browser"}
          >
            <RemoteBrowserPage embedded isVisible={browserVisible} />
          </div>
        )}
        {isMounted("terminal") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "terminal" ? "flex" : "none" }}
            aria-hidden={activeTab !== "terminal"}
          >
            <TerminalPage embedded isVisible={terminalVisible} />
          </div>
        )}
        {isMounted("cloud") && (
          <div
            className={styles.panel}
            style={{ display: activeTab === "cloud" ? "flex" : "none" }}
            aria-hidden={activeTab !== "cloud"}
          >
            <CloudHostsPage isVisible={isVisible && activeTab === "cloud"} />
          </div>
        )}
      </div>
    </PageShell>
  );
}
