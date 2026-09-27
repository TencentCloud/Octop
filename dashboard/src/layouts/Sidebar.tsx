import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import AvatarDropdown from "../components/AvatarDropdown";
import AppVersionBadge from "../components/AppVersionBadge";
import CurrentVersionBadge from "../components/CurrentVersionBadge";
import { ArrowRightLeft, ChevronDown, X } from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import { useLayoutMode } from "../context/LayoutModeContext";
import { useUserRole } from "../hooks/useUserRole";
import { useCurrentUser, useSetCurrentUser } from "../hooks/useCurrentUser";
import { useUpdateStatus } from "../hooks/useUpdateStatus";
import { prefetchRoute } from "../routes/prefetch";
import { useServerCapabilities } from "../hooks/useServerCapabilities";
import { useChatSidebarOpen } from "../pages/Chat/hooks/useChatSidebarState";
import { EXPAND_CHAT_RAIL_EVENT } from "../pages/Chat/components/ChatSidebarPanel";
import {
  CHAT_HISTORY_RAIL_ID,
  OPEN_NAV_RECORDS_EVENT,
  isChatPath,
} from "./chatHistoryRail";
import type { MinimalNavPane } from "./layoutModeStorage";
import MinimalRecordsHost from "./MinimalRecordsHost";
import SidebarCollapsedIconNav from "./SidebarCollapsedIconNav";
import SidebarMinimalPaneToggle from "./SidebarMinimalPaneToggle";
import { preferencesApi } from "../api/modules/preferences";
import {
  COLLAPSED_WIDTH,
  EXPANDED_WIDTH,
  buildNavSections,
  navSectionLabel,
  type NavItem,
  type NavSection,
} from "./sidebarNav";
import { sectionsFromLayout, type SidebarNavLayout } from "./sidebarNavLayout";
import SidebarNavCustomizer from "./SidebarNavCustomizer";
import styles from "./Sidebar.module.less";
import { typeSize } from "../utils/mobileTypeScale";
import { DESKTOP_DRAG_REGION_CLASS } from "../utils/desktopChrome";

const NAV_GROUPS_STORAGE_KEY = "octop:sidebar-nav-groups";
const LEGACY_COLLAPSED_GROUP_IDS: Record<string, string> = {
  "nav.settings": "settings",
  "nav.control": "control",
  "nav.admin": "admin",
};

function loadCollapsedGroups(): Set<string> {
  try {
    const raw = localStorage.getItem(NAV_GROUPS_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return new Set(
        parsed
          .filter((x): x is string => typeof x === "string")
          .map((id) => LEGACY_COLLAPSED_GROUP_IDS[id] ?? id),
      );
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
  const activeGroupId = navSections.find(
    (section) =>
      section.id && section.items.some((item) => item.key === selectedKey),
  )?.id;

  const toggleGroup = useCallback((groupId: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      saveCollapsedGroups(next);
      return next;
    });
  }, []);

  const isGroupCollapsed = useCallback(
    (groupId: string) => collapsedGroups.has(groupId),
    [collapsedGroups],
  );

  useEffect(() => {
    if (!activeGroupId) return;
    setCollapsedGroups((prev) => {
      if (!prev.has(activeGroupId)) return prev;
      const next = new Set(prev);
      next.delete(activeGroupId);
      saveCollapsedGroups(next);
      return next;
    });
  }, [activeGroupId, selectedKey]);

  return { toggleGroup, isGroupCollapsed };
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
  onExpandChatRail,
  showChatRailExpand,
  role,
  hasUpdate,
  t,
}: {
  item: NavItem;
  active: boolean;
  isMobile?: boolean;
  onNavigate: (path: string) => void;
  onExpandChatRail?: () => void;
  showChatRailExpand?: boolean;
  role: string | null;
  hasUpdate: boolean;
  t: TFunction<"translation", undefined>;
}) {
  const showExpand = Boolean(
    showChatRailExpand && item.key === "chat" && onExpandChatRail,
  );

  return (
    <div
      className={styles.navItemRow}
      style={{
        background: active ? "var(--fn-sidebar-item-active-bg)" : "transparent",
      }}
      onMouseEnter={(e) => {
        prefetchRoute(item.path);
        if (!active) {
          e.currentTarget.style.background = "var(--fn-sidebar-item-hover)";
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          e.currentTarget.style.background = "transparent";
        }
      }}
    >
      <button
        type="button"
        className={styles.navItemMain}
        onClick={() => onNavigate(item.path)}
        style={{
          color: active
            ? "var(--fn-sidebar-item-active-text)"
            : "var(--fn-text-secondary)",
          fontSize: typeSize(14, isMobile),
          fontWeight: active ? 500 : 400,
          paddingRight: showExpand ? 4 : 12,
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
            minWidth: 0,
          }}
        >
          {t(item.labelKey)}
          {item.key === "admin-advanced" && role === "admin" && hasUpdate ? (
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
      {showExpand ? (
        <button
          type="button"
          className={styles.chatRailExpandBtn}
          onClick={(e) => {
            e.stopPropagation();
            onExpandChatRail?.();
          }}
          aria-label={t("chat.expandHistorySidebar", "展开对话历史")}
          title={t("chat.expandHistorySidebar", "展开对话历史")}
        >
          <ArrowRightLeft size={14} strokeWidth={1.8} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

function NavList({
  sections,
  selectedKey,
  onNavigate,
  onExpandChatRail,
  showChatRailExpand,
  isMobile,
  isGroupCollapsed,
  toggleGroup,
  sectionFilter = "all",
  /** Group ids whose headers are omitted (items still render). */
  hideHeaderIds,
}: {
  sections: NavSection[];
  selectedKey: string;
  onNavigate: (path: string) => void;
  onExpandChatRail?: () => void;
  showChatRailExpand?: boolean;
  isMobile?: boolean;
  isGroupCollapsed: (groupId: string) => boolean;
  toggleGroup: (groupId: string) => void;
  /** all = classic; primary = ungrouped; grouped = named groups */
  sectionFilter?: "all" | "primary" | "grouped";
  hideHeaderIds?: ReadonlySet<string>;
}) {
  const { t } = useTranslation();
  const role = useUserRole();
  const { hasUpdate } = useUpdateStatus();
  const navSections = sections.filter((section) => {
    if (sectionFilter === "primary") return !section.id;
    if (sectionFilter === "grouped") return Boolean(section.id);
    return true;
  });

  const MOBILE_HIDDEN_KEYS = new Set<string>();

  return (
    <div
      style={{
        padding:
          sectionFilter === "grouped"
            ? "0 12px 8px"
            : sectionFilter === "primary"
            ? "8px 12px 0"
            : "8px 12px",
      }}
    >
      {navSections.map((section, sectionIndex) => {
        const visibleItems = isMobile
          ? section.items.filter((item) => !MOBILE_HIDDEN_KEYS.has(item.key))
          : section.items;
        if (visibleItems.length === 0) return null;

        const sectionKey = section.id ?? `flat-${sectionIndex}`;
        const hideHeader = Boolean(
          section.id && hideHeaderIds?.has(section.id),
        );
        const isFlat = !section.id || hideHeader;
        const groupCollapsed = section.id
          ? isGroupCollapsed(section.id)
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
                    onExpandChatRail={onExpandChatRail}
                    showChatRailExpand={showChatRailExpand}
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
              onClick={() => toggleGroup(section.id!)}
              aria-expanded={!groupCollapsed}
            >
              <span className={styles.navGroupLabel}>
                {navSectionLabel(section, t)}
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
                    onExpandChatRail={onExpandChatRail}
                    showChatRailExpand={showChatRailExpand}
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
  const location = useLocation();
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const role = useUserRole();
  const user = useCurrentUser();
  const setUser = useSetCurrentUser();
  const { hasUpdate } = useUpdateStatus();
  const { mobileEnabled } = useServerCapabilities();
  const { layoutMode, minimalPane, setMinimalPane } = useLayoutMode();
  const isMinimal = layoutMode === "minimal";
  const onChatPath = isChatPath(location.pathname);
  const catalog = useMemo(
    () => buildNavSections(user, { mobileEnabled }),
    [user, mobileEnabled],
  );
  const [savedLayout, setSavedLayout] = useState<SidebarNavLayout | null>(null);
  const [customizerOpen, setCustomizerOpen] = useState(false);
  const navSections = useMemo(
    () => sectionsFromLayout(catalog, savedLayout),
    [catalog, savedLayout],
  );
  const { toggleGroup, isGroupCollapsed } = useNavGroupCollapse(
    navSections,
    selectedKey,
  );

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    void preferencesApi
      .get()
      .then((prefs) => {
        if (!cancelled) setSavedLayout(prefs.sidebar_nav ?? null);
      })
      .catch(() => {
        /* keep the default nav */
      });
    return () => {
      cancelled = true;
    };
  }, [user]);
  const [chatSidebarOpen, setChatSidebarOpen] = useChatSidebarOpen();
  const showChatRailExpand = !isMinimal && !chatSidebarOpen;

  const isRailCollapsed = collapsed && !isMobile;
  const wordmarkSrc = isDark
    ? "/logo_horizontal_white.png"
    : "/logo_horizontal_dark.png";

  const selectMinimalPane = useCallback(
    (pane: MinimalNavPane, opts?: { expand?: boolean }) => {
      setMinimalPane(pane);
      if (opts?.expand && collapsed) {
        onToggle();
      }
    },
    [collapsed, onToggle, setMinimalPane],
  );

  // Pane choice is user-controlled; do not flip 记录/设置 when the route changes.
  // Both records-open events map to the same pane switch in minimal mode.
  useEffect(() => {
    if (!isMinimal) return;
    const handler = () => {
      selectMinimalPane("records", { expand: true });
    };
    window.addEventListener(OPEN_NAV_RECORDS_EVENT, handler);
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, handler);
    return () => {
      window.removeEventListener(OPEN_NAV_RECORDS_EVENT, handler);
      window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, handler);
    };
  }, [isMinimal, selectMinimalPane]);

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

  const handleExpandChatRail = useCallback(() => {
    if (isMinimal) {
      selectMinimalPane("records", { expand: true });
      return;
    }
    window.dispatchEvent(new Event(EXPAND_CHAT_RAIL_EVENT));
    setChatSidebarOpen(true);
    if (!window.location.pathname.startsWith("/chat")) {
      navigate("/chat");
    }
    if (isMobile) onToggle();
  }, [
    isMinimal,
    isMobile,
    navigate,
    onToggle,
    selectMinimalPane,
    setChatSidebarOpen,
  ]);

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
      {!isRailCollapsed && !isMobile && (
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
        onBeforeOpenSettings={isMobile && !collapsed ? onToggle : undefined}
        onCustomizeNav={() => setCustomizerOpen(true)}
      />
    </div>
  );

  const customizer = (
    <SidebarNavCustomizer
      open={customizerOpen}
      catalog={catalog}
      layout={savedLayout}
      onClose={() => setCustomizerOpen(false)}
      onSaved={setSavedLayout}
    />
  );

  const primaryItems = navSections.find((section) => !section.id)?.items ?? [];
  const namedSections = navSections.filter((section) => section.id);
  const firstNamed = namedSections[0];
  const settingsPaneLabel = firstNamed ? navSectionLabel(firstNamed, t) : null;
  const groupedItems = namedSections.flatMap((section) =>
    section.id && isGroupCollapsed(section.id) ? [] : section.items,
  );

  useEffect(() => {
    if (isMinimal && !settingsPaneLabel && minimalPane === "settings") {
      setMinimalPane("records");
    }
  }, [isMinimal, settingsPaneLabel, minimalPane, setMinimalPane]);

  const paneToggle = settingsPaneLabel ? (
    <SidebarMinimalPaneToggle
      settingsLabel={settingsPaneLabel}
      minimalPane={minimalPane}
      collapsed={isRailCollapsed}
      onSelect={selectMinimalPane}
    />
  ) : null;

  const classicNavBody = isRailCollapsed ? (
    <div style={{ padding: "8px 0" }}>
      <SidebarCollapsedIconNav
        items={navSections.flatMap((section) => {
          if (section.id && isGroupCollapsed(section.id)) {
            return [];
          }
          return section.items;
        })}
        selectedKey={selectedKey}
        onNavigate={handleNavigate}
        role={role}
        hasUpdate={hasUpdate}
        t={t}
      />
    </div>
  ) : (
    <NavList
      sections={navSections}
      selectedKey={selectedKey}
      onNavigate={handleNavigate}
      onExpandChatRail={handleExpandChatRail}
      showChatRailExpand={showChatRailExpand}
      isMobile={isMobile}
      isGroupCollapsed={isGroupCollapsed}
      toggleGroup={toggleGroup}
    />
  );

  const minimalNavBody = (
    <div className={styles.minimalNavBody}>
      {isRailCollapsed ? (
        <div style={{ padding: "8px 0", flexShrink: 0 }}>
          <SidebarCollapsedIconNav
            items={primaryItems}
            selectedKey={selectedKey}
            onNavigate={handleNavigate}
            role={role}
            hasUpdate={hasUpdate}
            t={t}
          />
          {paneToggle}
          {minimalPane === "settings" ? (
            <SidebarCollapsedIconNav
              items={groupedItems}
              selectedKey={selectedKey}
              onNavigate={handleNavigate}
              role={role}
              hasUpdate={hasUpdate}
              t={t}
            />
          ) : null}
        </div>
      ) : (
        <>
          <div className={styles.minimalPrimaryBlock}>
            <NavList
              sections={navSections}
              selectedKey={selectedKey}
              onNavigate={handleNavigate}
              onExpandChatRail={handleExpandChatRail}
              showChatRailExpand={false}
              isMobile={isMobile}
              isGroupCollapsed={isGroupCollapsed}
              toggleGroup={toggleGroup}
              sectionFilter="primary"
            />
            {paneToggle}
          </div>
          <div
            className={styles.minimalSettingsPane}
            hidden={minimalPane !== "settings"}
          >
            <NavList
              sections={navSections}
              selectedKey={selectedKey}
              onNavigate={handleNavigate}
              isMobile={isMobile}
              isGroupCollapsed={isGroupCollapsed}
              toggleGroup={toggleGroup}
              sectionFilter="grouped"
              hideHeaderIds={
                firstNamed?.id ? new Set([firstNamed.id]) : undefined
              }
            />
          </div>
        </>
      )}
      {/*
        Chat route: empty mount point — Chat portals live sessions here.
        Other routes: MinimalRecordsHost keeps expert/session nav available.
      */}
      <div
        id={CHAT_HISTORY_RAIL_ID}
        className={styles.minimalRecordsPane}
        hidden={isRailCollapsed || minimalPane !== "records"}
      >
        {!onChatPath ? <MinimalRecordsHost /> : null}
      </div>
    </div>
  );

  const navScrollBody = isMinimal ? minimalNavBody : classicNavBody;

  // Mobile: fixed overlay drawer
  if (isMobile) {
    return (
      <div
        style={{
          position: "fixed",
          top: 0,
          bottom: 0,
          left: 0,
          height: "auto",
          width: EXPANDED_WIDTH,
          boxSizing: "border-box",
          paddingLeft: "env(safe-area-inset-left, 0px)",
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
        <div
          style={{
            // Match Header: iOS PWA draws under the status bar (#664).
            height: "calc(56px + env(safe-area-inset-top, 0px))",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "env(safe-area-inset-top, 0px) 12px 0 16px",
            boxSizing: "border-box",
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
            aria-label={t("nav.collapseSidebar")}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 32,
              height: 32,
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

        <div
          style={{
            flex: 1,
            overflow:
              isMinimal && minimalPane === "records" ? "hidden" : "auto",
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {navScrollBody}
        </div>

        <div
          style={{
            paddingBottom: "calc(8px + env(safe-area-inset-bottom, 0px))",
          }}
        >
          {userFooter}
          {customizer}
        </div>
      </div>
    );
  }

  // Desktop: custom sidebar with icon-only collapsed mode.
  // Right border is drawn by MainLayout's RailEdgeControl.
  return (
    <div
      style={{
        width: isRailCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
        minWidth: isRailCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
        background: "var(--fn-sidebar-bg)",
        borderRight: "none",
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
        className={`${styles.sidebarBrand} ${DESKTOP_DRAG_REGION_CLASS}`}
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

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: isMinimal && minimalPane === "records" ? "hidden" : "auto",
          overflowX: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {navScrollBody}
      </div>

      {userFooter}
      {customizer}
    </div>
  );
}
