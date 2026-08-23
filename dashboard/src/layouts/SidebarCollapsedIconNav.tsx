import type { TFunction } from "i18next";
import { Tooltip } from "antd";
import { prefetchRoute } from "../routes/prefetch";
import { COLLAPSED_WIDTH, type NavItem } from "./sidebarNav";
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
  role: "admin" | "user" | null;
  hasUpdate: boolean;
  t: TFunction<"translation", undefined>;
}) {
  return (
    <>
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
              onClick={() => onNavigate(item.path)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: COLLAPSED_WIDTH,
                height: 40,
                border: "none",
                background: active
                  ? "var(--fn-sidebar-item-active-bg)"
                  : "transparent",
                color: active
                  ? "var(--fn-sidebar-item-active-text)"
                  : "var(--fn-text-tertiary)",
                cursor: "pointer",
                transition: "all var(--fn-transition-fast)",
                marginBottom: 2,
                position: "relative",
              }}
              onMouseEnter={(e) => {
                prefetchRoute(item.path);
                if (!active) {
                  e.currentTarget.style.background =
                    "var(--fn-sidebar-item-hover)";
                  e.currentTarget.style.color = "var(--fn-text-primary)";
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = "var(--fn-text-tertiary)";
                }
              }}
            >
              {item.icon}
              {showUpdateBadge ? (
                <span
                  className={`${styles.navUpdateBadge} ${styles.navUpdateBadgeCollapsed}`}
                >
                  新
                </span>
              ) : null}
              {item.badge && (
                <span
                  className="nav-badge-new nav-badge-new--collapsed"
                  style={{
                    position: "absolute",
                    top: 4,
                    right: 6,
                    zIndex: 2,
                    fontSize: 7,
                    fontWeight: 700,
                    color: "#fff",
                    backgroundColor: "#ff4d4f",
                    width: 14,
                    height: 14,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: "50%",
                    lineHeight: 1,
                    pointerEvents: "none",
                  }}
                >
                  {item.badge.charAt(0).toUpperCase()}
                </span>
              )}
            </button>
          </Tooltip>
        );
      })}
    </>
  );
}
