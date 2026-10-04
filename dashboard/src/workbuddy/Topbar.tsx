import type { ReactNode } from "react";
import { Menu } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../hooks/useIsMobile";
import {
  DESKTOP_DRAG_REGION_CLASS,
  DESKTOP_NO_DRAG_CLASS,
} from "../utils/desktopChrome";

export default function WorkBuddyTopbar({
  title,
  actions,
}: {
  title: ReactNode;
  actions?: ReactNode;
}) {
  const isMobile = useIsMobile();
  const { t } = useTranslation();
  return (
    <header
      className={`workbuddy-topbar ${DESKTOP_DRAG_REGION_CLASS}`}
      style={{
        paddingInlineEnd: "max(12px, var(--window-controls-inset-end, 0px))",
      }}
    >
      <div className="workbuddy-topbar-left">
        {isMobile && (
          <button
            className={`wb-topbar-navigation ${DESKTOP_NO_DRAG_CLASS}`}
            type="button"
            aria-label={t("nav.expandSidebar")}
            onClick={() => window.dispatchEvent(new Event("octop:toggle-nav"))}
          >
            <Menu size={18} />
          </button>
        )}
        {typeof title === "string" ? (
          <span
            className="workbuddy-topbar-title"
            role="heading"
            aria-level={1}
          >
            {title}
          </span>
        ) : (
          title
        )}
      </div>
      {actions && (
        <div className={`workbuddy-topbar-options ${DESKTOP_NO_DRAG_CLASS}`}>
          {actions}
        </div>
      )}
    </header>
  );
}
