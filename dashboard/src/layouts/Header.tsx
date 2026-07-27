import { Layout } from "antd";
import {
  Menu as MenuIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Github,
} from "lucide-react";
import PwaInstallPrompt from "../components/PwaInstallPrompt";
import pwaStyles from "../components/PwaInstallPrompt/index.module.less";
import ThemeSwitcher from "../components/ThemeSwitcher";
import { useTheme } from "../context/ThemeContext";
import { typeSize } from "../utils/mobileTypeScale";

const { Header: AntHeader } = Layout;

interface HeaderProps {
  selectedKey?: string;
  collapsed?: boolean;
  onToggle?: () => void;
  isMobile?: boolean;
}

/** Thin top chrome: mobile brand + sidebar toggle + GitHub / Install / theme. */
export default function Header({
  collapsed = false,
  onToggle,
  isMobile,
}: HeaderProps) {
  const { isDark } = useTheme();
  const mobileLogoSrc = isDark ? "/logo_name_dark.png" : "/logo_name.png";

  return (
    <AntHeader
      style={{
        height: "var(--fn-header-height)",
        padding: isMobile ? "0 12px" : "0 20px 0 4px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--fn-header-bg)",
        backdropFilter: "blur(var(--fn-header-blur))",
        WebkitBackdropFilter: "blur(var(--fn-header-blur))",
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
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: typeSize(34, !!isMobile),
              height: typeSize(34, !!isMobile),
              border: "none",
              borderRadius: "var(--fn-radius-md)",
              background: "transparent",
              color: "var(--fn-text-tertiary)",
              cursor: "pointer",
              transition: "all var(--fn-transition-fast)",
              flexShrink: 0,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--fn-bg-tertiary)";
              e.currentTarget.style.color = "var(--fn-text-secondary)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--fn-text-tertiary)";
            }}
          >
            {isMobile ? (
              <MenuIcon size={20} strokeWidth={1.8} />
            ) : collapsed ? (
              <PanelLeftOpen size={18} strokeWidth={1.8} />
            ) : (
              <PanelLeftClose size={18} strokeWidth={1.8} />
            )}
          </button>
        )}
        {isMobile && (
          <img
            src={mobileLogoSrc}
            alt="octop"
            style={{
              height: 36,
              width: "auto",
              maxWidth: 230,
              objectFit: "contain",
              flexShrink: 0,
              display: "block",
            }}
          />
        )}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: isMobile ? 4 : 10,
          flexShrink: 0,
        }}
      >
        {!isMobile && (
          <a
            href="https://github.com/TencentCloud/Octop"
            target="_blank"
            rel="noopener noreferrer"
            className={pwaStyles.installBtn}
          >
            <Github
              size={16}
              strokeWidth={1.8}
              className={pwaStyles.installIcon}
            />
            <span className={pwaStyles.label}>GitHub</span>
          </a>
        )}
        <PwaInstallPrompt compact={isMobile} />
        {!isMobile && <ThemeSwitcher compact />}
      </div>
    </AntHeader>
  );
}
