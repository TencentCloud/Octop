import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";
import ThemeSwitcher from "../components/ThemeSwitcher";
import {
  Monitor,
  MessageSquareText,
  Timer,
  SlidersHorizontal,
  X,
  PanelLeftClose,
  PanelLeftOpen,
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
import { prefetchRoute } from "../routes/prefetch";
import styles from "./Sidebar.module.less";
import { typeSize } from "../utils/mobileTypeScale";

const EXPANDED_WIDTH = 240;
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

function useNavGroupCollapse(navGroups: NavGroup[], selectedKey: string) {
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
    const activeGroup = navGroups.find((g) =>
      g.items.some((i) => i.key === selectedKey),
    );
    if (!activeGroup) return;
    setCollapsedGroups((prev) => {
      if (!prev.has(activeGroup.groupKey)) return prev;
      const next = new Set(prev);
      next.delete(activeGroup.groupKey);
      saveCollapsedGroups(next);
      return next;
    });
  }, [selectedKey, navGroups]);

  return { toggleGroup, isGroupCollapsed };
}

interface NavItem {
  key: string;
  path: string;
  icon: React.ReactNode;
  labelKey: string;
  badge?: string;
}

interface NavGroup {
  groupKey: string;
  items: NavItem[];
}

const iconSize = 16;
const iconStroke = 1.8;

function buildNavGroups(role: "admin" | "user" | null): NavGroup[] {
  const groups: NavGroup[] = [
    // ──────────────── Common ────────────────
    {
      groupKey: "nav.common",
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
          badge: "new",
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
          badge: "new",
        },
        {
          key: "skills",
          path: "/skills",
          icon: <Sparkles size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.skills",
        },
        {
          key: "token-usage",
          path: "/token-usage",
          icon: <Activity size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.tokenUsage",
        },
      ],
    },
    // ──────────────── Control ────────────────
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
          key: "subagents",
          path: "/subagents",
          icon: <Bot size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.subagents",
          badge: "new",
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
          badge: "new",
        },
        {
          key: "acp",
          path: "/acp",
          icon: <Share2 size={iconSize} strokeWidth={iconStroke} />,
          labelKey: "nav.acp",
          badge: "new",
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
    groups.push({
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
          badge: "new",
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
  return groups;
}

interface SidebarProps {
  selectedKey: string;
  collapsed: boolean;
  onToggle: () => void;
  isMobile?: boolean;
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
  const navGroups = buildNavGroups(role);

  // Keys to hide on mobile (these pages are not usable on small screens)
  const MOBILE_HIDDEN_KEYS = new Set<string>();

  return (
    <div style={{ padding: "8px 12px" }}>
      {navGroups.map((group) => {
        const visibleItems = isMobile
          ? group.items.filter((item) => !MOBILE_HIDDEN_KEYS.has(item.key))
          : group.items;
        if (visibleItems.length === 0) return null;
        const groupCollapsed = isGroupCollapsed(group.groupKey);
        return (
          <div key={group.groupKey} className={styles.navGroup}>
            <button
              type="button"
              className={styles.navGroupHeader}
              onClick={() => toggleGroup(group.groupKey)}
              aria-expanded={!groupCollapsed}
            >
              <span className={styles.navGroupLabel}>{t(group.groupKey)}</span>
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
                {visibleItems.map((item) => {
                  const active = selectedKey === item.key;
                  return (
                    <button
                      key={item.key}
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
                            "var(--fn-text-secondary)";
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
                        {item.key === "admin-updates" &&
                        role === "admin" &&
                        hasUpdate ? (
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
                })}
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
  const navGroups = buildNavGroups(role);
  const { toggleGroup, isGroupCollapsed } = useNavGroupCollapse(
    navGroups,
    selectedKey,
  );

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
            borderBottom: "1px solid var(--fn-sidebar-border)",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <img
              src={isDark ? "/logo_name_dark.png" : "/logo_name.png"}
              alt="Octop"
              style={{
                height: 38,
                width: "auto",
                maxWidth: 190,
                objectFit: "contain",
                display: "block",
              }}
            />
          </div>
          <button
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

        {/* Theme switcher at bottom of mobile drawer */}
        <div
          style={{
            flexShrink: 0,
            borderTop: "1px solid var(--fn-sidebar-border)",
            padding: "12px 16px calc(12px + env(safe-area-inset-bottom, 0px))",
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
      </div>
    );
  }

  // Desktop: custom sidebar with icon-only collapsed mode
  const isCollapsed = collapsed && !isMobile;

  return (
    <div
      style={{
        width: isCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
        minWidth: isCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
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
      {/* Nav items */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          overflowX: "hidden",
        }}
      >
        {isCollapsed ? (
          // Icon-only mode
          <div style={{ padding: "8px 0" }}>
            {(() => {
              let visibleGroupIndex = 0;
              return navGroups.flatMap((group) => {
                if (isGroupCollapsed(group.groupKey)) return [];
                const divider =
                  visibleGroupIndex > 0 ? (
                    <div
                      key={`divider-${group.groupKey}`}
                      style={{
                        height: 1,
                        background: "var(--fn-sidebar-border)",
                        margin: "4px 8px",
                      }}
                    />
                  ) : null;
                visibleGroupIndex += 1;
                const items = group.items.map((item) => {
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
                return divider ? [divider, ...items] : items;
              });
            })()}
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

      {/* Collapse toggle button at bottom */}
      <div
        style={{
          flexShrink: 0,
          borderTop: "1px solid var(--fn-sidebar-border)",
          padding: isCollapsed ? "8px 0" : "8px 12px",
          display: "flex",
          justifyContent: isCollapsed ? "center" : "flex-start",
        }}
      >
        <Tooltip
          title={
            isCollapsed
              ? t("nav.expandSidebar") || "展开"
              : t("nav.collapseSidebar") || "收起"
          }
          placement="right"
          mouseEnterDelay={0.4}
        >
          <button
            onClick={onToggle}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: isCollapsed ? "center" : "flex-start",
              gap: 8,
              width: isCollapsed ? 36 : "100%",
              height: 36,
              padding: isCollapsed ? "0" : "0 10px",
              border: "none",
              borderRadius: "var(--fn-radius-md)",
              background: "transparent",
              color: "var(--fn-text-tertiary)",
              cursor: "pointer",
              transition: "all var(--fn-transition-fast)",
              fontSize: 13,
              fontWeight: 500,
              whiteSpace: "nowrap",
              overflow: "hidden",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--fn-sidebar-item-hover)";
              e.currentTarget.style.color = "var(--fn-text-secondary)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--fn-text-tertiary)";
            }}
          >
            {isCollapsed ? (
              <PanelLeftOpen size={16} strokeWidth={1.8} />
            ) : (
              <>
                <PanelLeftClose size={16} strokeWidth={1.8} />
                <span>{t("nav.collapseSidebar") || "收起"}</span>
              </>
            )}
          </button>
        </Tooltip>
      </div>
    </div>
  );
}
