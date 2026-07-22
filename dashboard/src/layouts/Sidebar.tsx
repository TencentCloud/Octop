import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Tooltip } from "antd";
import ThemeSwitcher from "../components/ThemeSwitcher";
import AvatarDropdown from "../components/AvatarDropdown";
import AppVersionBadge from "../components/AppVersionBadge";
import CurrentVersionBadge from "../components/CurrentVersionBadge";
import {
  Monitor,
  MessageSquareText,
  Timer,
  SlidersHorizontal,
  X,
  PlugZap,
  Link2,
  Database,
  Users as UsersIcon,
  ScrollText,
  Activity,
  TerminalSquare,
  Globe,
  Share2,
  Sparkles,
  Puzzle,
  FolderOpen,
  GraduationCap,
  Brain,
  Notebook,
  Bot,
  ChevronDown,
  RefreshCw,
  Shield,
} from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import { useUserRole } from "../hooks/useUserRole";
import { useUpdateStatus } from "../hooks/useUpdateStatus";
import { authApi } from "../api/modules/auth";
import type { OctopUser } from "../api/modules/auth";
import { prefetchRoute } from "../routes/prefetch";
import styles from "./Sidebar.module.less";
import { typeSize } from "../utils/mobileTypeScale";

const EXPANDED_WIDTH = 220;
const COLLAPSED_WIDTH = 56;
const NAV_GROUPS_STORAGE_KEY = "octop:sidebar-nav-groups";

function loadCollapsedGroups(): Set<string> {
  try {
    const raw = localStorage.getItem(NAV_GROUPS_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((x): x is string => typeof x === "string"));
    }
  } catch {
    /* ignore */
  }
  return new Set();
}

function saveCollapsedGroups(collapsed: Set<string>) {
  try {
    localStorage.setItem(
      NAV_GROUPS_STORAGE_KEY,
      JSON.stringify([...collapsed]),
    );
  } catch {
    /* ignore */
  }
}

function useNavGroupCollapse(navSections: NavSection[], selectedKey: string) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() =>
    loadCollapsedGroups(),
  );

  const toggleGroup = useCallback((groupKey: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      saveCollapsedGroups(next);
      return next;
    });
  }, []);

  const isGroupCollapsed = useCallback(
    (groupKey: string) => collapsedGroups.has(groupKey),
    [collapsedGroups],
  );

  useEffect(() => {
    const activeSection = navSections.find(
      (section) =>
        section.groupKey &&
        section.items.some((item) => item.key === selectedKey),
    );
    if (!activeSection?.groupKey) return;
    setCollapsedGroups((prev) => {
      if (!prev.has(activeSection.groupKey!)) return prev;
      const next = new Set(prev);
      next.delete(activeSection.groupKey!);
      saveCollapsedGroups(next);
      return next;
    });
  }, [selectedKey, navSections]);

  return { toggleGroup, isGroupCollapsed };
}

interface NavItem {
  key: string;
  path: string;
  icon: React.ReactNode;
  labelKey: string;
  badge?: string;
}

interface NavSection {
  /** When omitted, items render flat without a group header. */
  groupKey?: string;
  items: NavItem[];
}

const iconSize = 16;
const iconStroke = 1.8;

function buildNavSections(role: "admin" | "user" | null): NavSection[] {
  const sections: NavSection[] = [
    {
      items: [
        {
          key: "chat",
          path: "/chat",
          icon: <MessageSquareText size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.chat",
        },
        {
          key: "experts",
          path: "/experts",
          icon: <GraduationCap size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.experts",
        },
        {
          key: "tasks",
          path: "/tasks",
          icon: <Timer size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.tasks",
        },
        {
          key: "connectors",
          path: "/connectors",
          icon: <Link2 size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.connectors",
        },
        {
          key: "token-usage",
          path: "/token-usage",
          icon: <Activity size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.tokenUsage",
        },
      ],
    },
    {
      groupKey: "nav.control",
      items: [
        {
          key: "channels",
          path: "/channels",
          icon: <PlugZap size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.channels",
        },
        {
          key: "skills",
          path: "/skills",
          icon: <Sparkles size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.skills",
        },
        {
          key: "subagents",
          path: "/subagents",
          icon: <Bot size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.subagents",
        },
        {
          key: "terminal",
          path: "/terminal",
          icon: <TerminalSquare size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.terminal",
        },
        {
          key: "remote-browser",
          path: "/remote-browser",
          icon: <Globe size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.remoteBrowser",
        },
        {
          key: "remote-desktop",
          path: "/remote-desktop",
          icon: <Monitor size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.remoteDesktop",
        },
        {
          key: "acp",
          path: "/acp",
          icon: <Share2 size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.acp",
        },
        {
          key: "mbti",
          path: "/mbti",
          icon: <Brain size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.mbti",
        },
        {
          key: "memory",
          path: "/memory",
          icon: <Notebook size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.memory",
        },
      ],
    },
  ];

  if (role === "admin") {
    sections.push({
      groupKey: "nav.admin",
      items: [
        {
          key: "admin-users",
          path: "/admin/users",
          icon: <UsersIcon size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.adminUsers",
        },
        {
          key: "models",
          path: "/admin/models",
          icon: <Database size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.models",
        },
        {
          key: "admin-storage",
          path: "/admin/backend",
          icon: <FolderOpen size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.adminStorage",
        },
        {
          key: "admin-audit",
          path: "/admin/audit",
          icon: <ScrollText size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.adminAudit",
        },
        {
          key: "admin-plugins",
          path: "/admin/plugins",
          icon: <Puzzle size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.adminPlugins",
        },
        {
          key: "admin-security",
          path: "/admin/security",
          icon: <Shield size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.security",
        },
        {
          key: "admin-advanced",
          path: "/admin/advanced",
          icon: <SlidersHorizontal size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.adminAdvanced",
        },
        {
          key: "admin-updates",
          path: "/admin/updates",
          icon: <RefreshCw size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.checkUpdates",
        },
      ],
    });
  }
  return sections;
}

interface SidebarProps {
  selectedKey: string;
  collapsed: boolean;
  onToggle: () => void;
  isMobile?: boolean;
}

function NavItemButton({
  item,
  active,
  isMobile,
  onNavigate,
  role,
  hasUpdate,
  t,
}: {
  item: NavItem;
  active: boolean;
  isMobile?: boolean;
  onNavigate: (path: string) => void;
  role: "admin" | "user" | null;
  hasUpdate: boolean;
  t: TFunction<"translation", undefined>;
}) {
  return (
    <button
      type="button"
      onClick={() => onNavigate(item.path)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        padding: "0 12px",
        height: 40,
        border: "none",
        borderRadius: "var(--fn-radius-md)",
        background: active
          ? "var(--fn-sidebar-item-active-bg)"
          : "transparent",
        color: active
          ? "var(--fn-sidebar-item-active-text)"
          : "var(--fn-text-secondary)",
        cursor: "pointer",
        fontSize: typeSize(14, isMobile),
        fontWeight: active ? 500 : 400,
        textAlign: "left",
        transition: "all var(--fn-transition-fast)",
        marginBottom: 2,
      }}
      onMouseEnter={(e) => {
        prefetchRoute(item.path);
        if (!active) {
          e.currentTarget.style.background = "var(--fn-sidebar-item-hover)";
          e.currentTarget.style.color = "var(--fn-text-primary)";
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          e.currentTarget.style.background = "transparent";
          e.currentTarget.style.color = "var(--fn-text-secondary)";
        }
      }}
    >
      <span
        style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          color: active
            ? "var(--fn-sidebar-item-active-text)"
            : "var(--fn-text-tertiary)",
        }}
      >
        {item.icon}
      </span>
      <span
        style={{
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {t(item.labelKey)}
        {item.key === "admin-updates" && role === "admin" && hasUpdate ? (
          <span className={styles.navUpdateBadge}>
            {t("nav.newVersionBadge", "有新版本")}
          </span>
        ) : null}
        {item.badge && (
          <span
            className="nav-badge-new"
            style={{
              fontSize: typeSize(9, isMobile),
              fontWeight: 600,
              color: "#fff",
              backgroundColor: "#ff4d4f",
              padding: "1px 4px",
              borderRadius: "2px",
              whiteSpace: "nowrap",
              flexShrink: 0,
              textTransform: "uppercase",
              lineHeight: 1.2,
              letterSpacing: "0.5px",
            }}
          >
            {item.badge}
          </span>
        )}
      </span>
    </button>
  );
}

function NavList({
  selectedKey,
  onNavigate,
  isMobile,
  isGroupCollapsed,
  toggleGroup,
}: {
  selectedKey: string;
  onNavigate: (path: string) => void;
  isMobile?: boolean;
  isGroupCollapsed: (groupKey: string) => boolean;
  toggleGroup: (groupKey: string) => void;
}) {
  const { t } = useTranslation();
  const role = useUserRole();
  const { hasUpdate } = useUpdateStatus();
  const navSections = buildNavSections(role);

  const MOBILE_HIDDEN_KEYS = new Set<string>();

  return (
    <div style={{ padding: "8px 12px" }}>
      {navSections.map((section, sectionIndex) => {
        const visibleItems = isMobile
          ? section.items.filter((item) => !MOBILE_HIDDEN_KEYS.has(item.key))
          : section.items;
        if (visibleItems.length === 0) return null;

        const sectionKey = section.groupKey ?? `flat-${sectionIndex}`;
        const isFlat = !section.groupKey;
        const groupCollapsed = section.groupKey
          ? isGroupCollapsed(section.groupKey)
          : false;

        if (isFlat) {
          return (
            <div key={sectionKey} className={styles.navGroup}>
              <div className={styles.navGroupItems}>
                {visibleItems.map((item) => (
                  <NavItemButton
                    key={item.key}
                    item={item}
                    active={selectedKey === item.key}
                    isMobile={isMobile}
                    onNavigate={onNavigate}
                    role={role}
                    hasUpdate={hasUpdate}
                    t={t}
                  />
                ))}
              </div>
            </div>
          );
        }

        return (
          <div key={sectionKey} className={styles.navGroup}>
            <button
              type="button"
              className={styles.navGroupHeader}
              onClick={() => toggleGroup(section.groupKey!)}
              aria-expanded={!groupCollapsed}
            >
              <span className={styles.navGroupLabel}>
                {t(section.groupKey!)}
              </span>
              <ChevronDown
                size={12}
                strokeWidth={2}
                className={`${styles.navGroupChevron} ${
                  groupCollapsed ? styles.navGroupChevronFolded : ""
                }`}
                aria-hidden
              />
            </button>

            {!groupCollapsed && (
              <div className={styles.navGroupItems}>
                {visibleItems.map((item) => (
                  <NavItemButton
                    key={item.key}
                    item={item}
                    active={selectedKey === item.key}
                    isMobile={isMobile}
                    onNavigate={onNavigate}
                    role={role}
                    hasUpdate={hasUpdate}
                    t={t}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function Sidebar({
  selectedKey,
  collapsed,
  onToggle,
  isMobile,
}: SidebarProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const role = useUserRole();
  const { hasUpdate } = useUpdateStatus();
  const navSections = buildNavSections(role);
  const { toggleGroup, isGroupCollapsed } = useNavGroupCollapse(
    navSections,
    selectedKey,
  );
  const [user, setUser] = useState<OctopUser | null>(null);

  useEffect(() => {
    authApi
      .me()
      .then(setUser)
      .catch(() => {});
  }, []);

  const isRailCollapsed = collapsed && !isMobile;
  const wordmarkSrc = isDark ? "/logo_name_dark.png" : "/logo_name.png";

  const handleNavigate = (path: string) => {
    // When navigating to /chat, preserve the current chatId in the URL so the
    // Chat component is not remounted (key stays the same) and the user stays
    // on their most recent conversation instead of seeing a blank welcome screen.
    if (path === "/chat" && window.location.pathname.startsWith("/chat/")) {
      if (isMobile) onToggle();
      return;
    }
    navigate(path);
    if (isMobile) onToggle();
  };

  const brandInner = (
    <>
      <img
        src={isRailCollapsed ? "/pwa-192.png" : wordmarkSrc}
        alt="Octop"
        style={{
          height: isRailCollapsed ? 32 : isMobile ? 38 : 36,
          width: isRailCollapsed ? 32 : "auto",
          maxWidth: isRailCollapsed ? 32 : isMobile ? 190 : 160,
          objectFit: "contain",
          display: "block",
          flexShrink: 0,
          borderRadius: isRailCollapsed ? 8 : undefined,
        }}
      />
      {!isRailCollapsed && (
        <>
          <CurrentVersionBadge isMobile={isMobile} />
          <AppVersionBadge isMobile={isMobile} />
        </>
      )}
    </>
  );

  const userFooter = (
    <div
      className={styles.sidebarUser}
      style={{
        flexShrink: 0,
        padding: isRailCollapsed ? "10px 0" : "10px 12px",
        display: "flex",
        justifyContent: isRailCollapsed ? "center" : "stretch",
      }}
    >
      <AvatarDropdown
        user={user}
        onUserChange={setUser}
        placement="sidebar"
        compact={isRailCollapsed}
      />
    </div>
  );

  // Mobile: fixed overlay drawer
  if (isMobile) {
    return (
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          height: "100dvh",
          width: EXPANDED_WIDTH,
          background: "var(--fn-sidebar-bg)",
          borderRight: "1px solid var(--fn-sidebar-border)",
          zIndex: 100,
          display: "flex",
          flexDirection: "column",
          transform: collapsed ? "translateX(-100%)" : "translateX(0)",
          transition: "transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
          boxShadow: collapsed ? "none" : "4px 0 20px rgba(0,0,0,0.10)",
        }}
      >
        {/* Logo + close */}
        <div
          style={{
            height: 56,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 12px 0 16px",
            flexShrink: 0,
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              minWidth: 0,
              flex: 1,
            }}
          >
            {brandInner}
          </div>
          <button
            type="button"
            onClick={onToggle}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 30,
              height: 30,
              border: "none",
              borderRadius: "var(--fn-radius-md)",
              background: "transparent",
              color: "var(--fn-text-tertiary)",
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div style={{ flex: 1, overflow: "auto" }}>
          <NavList
            selectedKey={selectedKey}
            onNavigate={handleNavigate}
            isMobile={isMobile}
            isGroupCollapsed={isGroupCollapsed}
            toggleGroup={toggleGroup}
          />
        </div>

        <div
          style={{
            flexShrink: 0,
            padding: "12px 16px 8px",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span
              style={{
                fontSize: typeSize(13, true),
                color: "var(--fn-text-tertiary)",
              }}
            >
              {t("nav.theme") || "主题"}
            </span>
            <ThemeSwitcher />
          </div>
        </div>
        <div
          style={{
            paddingBottom: "calc(8px + env(safe-area-inset-bottom, 0px))",
          }}
        >
          {userFooter}
        </div>
      </div>
    );
  }

  // Desktop: custom sidebar with icon-only collapsed mode
  return (
    <div
      style={{
        width: isRailCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
        minWidth: isRailCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
        background: "var(--fn-sidebar-bg)",
        borderRight: "1px solid var(--fn-sidebar-border)",
        transition:
          "width 0.25s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        alignSelf: "stretch",
        minHeight: 0,
      }}
    >
      <div
        className={styles.sidebarBrand}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          minWidth: 0,
          padding: isRailCollapsed ? "12px 0" : "14px 14px 10px",
          justifyContent: isRailCollapsed ? "center" : "flex-start",
          flexShrink: 0,
        }}
      >
        {brandInner}
      </div>

      {/* Nav items */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          overflowX: "hidden",
        }}
      >
        {isRailCollapsed ? (
          <div style={{ padding: "8px 0" }}>
            {navSections.flatMap((section) => {
              if (section.groupKey && isGroupCollapsed(section.groupKey)) {
                return [];
              }
              return section.items.map((item) => {
                const active = selectedKey === item.key;
                const showUpdateBadge =
                  item.key === "admin-updates" &&
                  role === "admin" &&
                  hasUpdate;
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
                      onClick={() => handleNavigate(item.path)}
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
                          e.currentTarget.style.color =
                            "var(--fn-text-primary)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!active) {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color =
                            "var(--fn-text-tertiary)";
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
              });
            })}
          </div>
        ) : (
          <NavList
            selectedKey={selectedKey}
            onNavigate={handleNavigate}
            isMobile={isMobile}
            isGroupCollapsed={isGroupCollapsed}
            toggleGroup={toggleGroup}
          />
        )}
      </div>

      {userFooter}
    </div>
  );
}
