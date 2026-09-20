import { Layout } from "antd";
import { Menu as MenuIcon } from "lucide-react";
import PwaInstallPrompt from "../components/PwaInstallPrompt";
import AppVersionBadge from "../components/AppVersionBadge";
import CurrentVersionBadge from "../components/CurrentVersionBadge";
import { useTheme } from "../context/ThemeContext";
import { typeSize } from "../utils/mobileTypeScale";

const { Header: AntHeader } = Layout;

interface HeaderProps {
  selectedKey?: string;
  collapsed?: boolean;
  onToggle?: () => void;
  isMobile?: boolean;
}

/**
 * Mobile-only top chrome: brand + nav toggle + install.
 * Desktop GitHub / theme controls moved into the account popover.
 */
export default function Header({ onToggle, isMobile }: HeaderProps) {
  const { isDark } = useTheme();
  const mobileLogoSrc = isDark ? "/logo_name_dark.png" : "/logo_name.png";

  if (!isMobile) return null;

  // iOS PWA (`apple-mobile-web-app-status-bar-style: black-translucent`) draws
  // under the status bar; pad the chrome so controls stay tappable (#664).
  const safeTop = "env(safe-area-inset-top, 0px)";

  return (
    <AntHeader
      style={{
        height: `calc(var(--fn-header-height) + ${safeTop})`,
        padding: `${safeTop} calc(12px + var(--window-controls-inset-end, 0px)) 0 12px`,
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--fn-header-bg)",
        // Opaque inset: translucent blur under `black-translucent` frosts
        // page content through the iOS status bar (#874).
        backdropFilter: "none",
        WebkitBackdropFilter: "none",
        borderBottom: "1px solid var(--fn-border-primary)",
        transition: "background var(--fn-transition)",
        flexShrink: 0,
        zIndex: 20,
      }}
    >
      <div
        style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}
      >
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-label="Open navigation"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: typeSize(34, true),
              height: typeSize(34, true),
              border: "none",
              borderRadius: "var(--fn-radius-md)",
              background: "transparent",
              color: "var(--fn-text-tertiary)",
              cursor: "pointer",
              transition: "all var(--fn-transition-fast)",
              flexShrink: 0,
            }}
          >
            <MenuIcon size={20} strokeWidth={1.8} />
          </button>
        )}
        <img
          src={mobileLogoSrc}
          alt="octop"
          style={{
            height: 36,
            width: "auto",
            maxWidth: 160,
            objectFit: "contain",
            flexShrink: 0,
            display: "block",
          }}
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            minWidth: 0,
            flexShrink: 1,
          }}
        >
          <CurrentVersionBadge isMobile />
          <AppVersionBadge isMobile />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          flexShrink: 0,
        }}
      >
        <PwaInstallPrompt compact />
      </div>
    </AntHeader>
  );
}
