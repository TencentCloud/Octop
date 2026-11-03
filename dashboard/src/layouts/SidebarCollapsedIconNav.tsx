import type { TFunction } from "i18next";
import { Tooltip } from "antd";
import cx from "classnames";
import { prefetchRoute } from "../routes/prefetch";
import type { NavItem } from "./sidebarNav";
import styles from "./Sidebar.module.less";

export default function SidebarCollapsedIconNav({
  items,
  selectedKey,
  onNavigate,
  role,
  hasUpdate,
  t,
}: {
  items: NavItem[];
  selectedKey: string;
  onNavigate: (path: string) => void;
  role: string | null;
  hasUpdate: boolean;
  t: TFunction<"translation", undefined>;
}) {
  return (
    <div className={styles.collapsedNav}>
      {items.map((item) => {
        const active = selectedKey === item.key;
        const showUpdateBadge =
          item.key === "admin-advanced" && role === "admin" && hasUpdate;
        return (
          <Tooltip
            key={item.key}
            title={`${t(item.labelKey)}${
              showUpdateBadge
                ? ` (${t("nav.newVersionBadge", "有新版本")})`
                : item.badge
                ? ` (${item.badge})`
                : ""
            }`}
            placement="right"
            mouseEnterDelay={0.2}
          >
            <button
              type="button"
              className={
                active
                  ? `${styles.collapsedNavBtn} ${styles.collapsedNavBtnActive}`
                  : styles.collapsedNavBtn
              }
              onClick={() => onNavigate(item.path)}
              onMouseEnter={() => prefetchRoute(item.path)}
              aria-label={t(item.labelKey)}
              aria-current={active ? "page" : undefined}
            >
              {item.icon}
              {showUpdateBadge ? (
                <span
                  className={cx(
                    styles.navUpdateBadge,
                    styles.navUpdateBadgeCollapsed,
                  )}
                >
                  {t("nav.newVersionBadgeShort", "新")}
                </span>
              ) : null}
              {item.badge && (
                <span
                  className={`nav-badge-new nav-badge-new--collapsed ${styles.collapsedNavBadge}`}
                >
                  {item.badge.charAt(0).toUpperCase()}
                </span>
              )}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
