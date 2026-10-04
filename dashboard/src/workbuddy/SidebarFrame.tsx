import type { ReactNode } from "react";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Production and visual fixtures share the same sidebar structure. */
export default function SidebarFrame({
  collapsed,
  onToggle,
  isMobile = false,
  navigation,
  history,
  footer,
  children,
}: {
  collapsed: boolean;
  onToggle: () => void;
  isMobile?: boolean;
  navigation: ReactNode;
  history: ReactNode;
  footer: ReactNode;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const compact = collapsed && !isMobile;
  return (
    <aside
      className={`conversation-list wb-shell-sidebar${
        compact ? " conversation-list-collapsed" : ""
      }${isMobile ? " wb-shell-sidebar--mobile" : ""}`}
      data-collapsed={collapsed}
      aria-label={t("workbuddy.workspace")}
      aria-hidden={isMobile && collapsed ? true : undefined}
    >
      <div className="wb-shell-sidebar__brand">
        <picture>
          <img
            className={compact ? undefined : "wb-shell-logo-light"}
            src={compact ? "/pwa-192.png" : "/logo_horizontal_dark.png"}
            alt="Octop"
          />
          {!compact && (
            <img
              className="wb-shell-logo-dark"
              src="/logo_horizontal_white.png"
              alt="Octop"
            />
          )}
        </picture>
        <button
          type="button"
          onClick={onToggle}
          aria-label={t(compact ? "nav.expandSidebar" : "nav.collapseSidebar")}
        >
          {isMobile ? (
            <X size={16} />
          ) : compact ? (
            <PanelLeftOpen size={16} />
          ) : (
            <PanelLeftClose size={16} />
          )}
        </button>
      </div>
      {navigation}
      <div
        className="conversation-list-content wb-shell-sidebar__history"
        hidden={compact}
      >
        {history}
      </div>
      <footer className="conversation-list-footer wb-shell-sidebar__footer">
        {footer}
      </footer>
      {children}
    </aside>
  );
}
