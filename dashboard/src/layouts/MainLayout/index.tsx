import { Layout } from "antd";
import { lazy, Suspense, useEffect, useState, useCallback } from "react";
import { Routes, Route, useLocation, useNavigate } from "react-router-dom";
import Sidebar from "../Sidebar";
import Header from "../Header";
import PageLoading from "../../components/PageLoading";
import { ServiceRestartProvider } from "../../context/ServiceRestartContext";
import { BackupOperationProvider } from "../../context/BackupOperationContext";
import { PwaAutoPrompt } from "../../components/PwaInstallPrompt";
import {
  routeConfigs,
  resolveSelectedKey,
  FULLSCREEN_PATHS,
  MOBILE_FULLSCREEN_PATHS,
  SELF_HEADER_PATHS,
  isWorkbenchPath,
} from "../../routes";
import { CHAT_HISTORY_RAIL_ID, isChatPath } from "../chatHistoryRail";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useKeyboardOffset } from "../../hooks/useKeyboardOffset";
import { useChatSidebarOpen } from "../../pages/Chat/hooks/useChatSidebarState";
import { EXPAND_CHAT_RAIL_EVENT } from "../../pages/Chat/chatRailEvents";
import RailEdgeControl from "../../components/RailEdgeControl";
import {
  isMacPlatform,
  railShortcutAria,
  railShortcutLabel,
} from "../../utils/railShortcuts";
import { useTranslation } from "react-i18next";
import DesktopWindowDragBand from "../../components/DesktopWindowDragBand";
import RequirePermission from "../../components/RequirePermission";
import { routeNeedsPermission } from "../../utils/permissions";
import { useLayoutMode } from "../../context/LayoutModeContext";
import { useDashboardPushToast } from "../../hooks/useDashboardPushToast";
import { useRailShortcuts } from "../../hooks/useRailShortcuts";
import { DESKTOP_CHROME_HEIGHT } from "../../utils/desktopChrome";

const Chat = lazy(() => import("../../pages/Chat"));
const WorkbenchPage = lazy(() => import("../../pages/Control/Workbench"));

const { Content } = Layout;

const SIDEBAR_COLLAPSED_KEY = "octop:sidebar:collapsed";

function getSavedCollapsed(): boolean {
  try {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (saved !== null) return saved === "true";
  } catch {
    // localStorage may be unavailable (e.g. private browsing restrictions)
  }
  return false; // Default: expanded on both desktop and mobile.
}

/**
 * Chat route wrapper. Intentionally does NOT key on threadId — switching
 * conversations updates URL params only; chatStore + useChat load history
 * per thread without remounting the whole page.
 */
function ChatWithKey() {
  return <Chat />;
}

export default function MainLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const currentPath = location.pathname;
  const selectedKey = resolveSelectedKey(currentPath);
  const isMobile = useIsMobile();
  const { layoutMode } = useLayoutMode();
  useDashboardPushToast();
  useKeyboardOffset();
  const isMinimalLayout = layoutMode === "minimal";
  const isFullscreen =
    FULLSCREEN_PATHS.has(currentPath) ||
    [...FULLSCREEN_PATHS].some((p) => currentPath.startsWith(p + "/")) ||
    (isMobile && MOBILE_FULLSCREEN_PATHS.has(currentPath));
  const onWorkbench = isWorkbenchPath(currentPath);
  // Web and desktop share one top row, not a native spacer + a page header.
  // Fullscreen keeps that layout but disables window dragging.
  const shellTopBand = isMobile ? 0 : DESKTOP_CHROME_HEIGHT;

  const [collapsed, setCollapsed] = useState(() => getSavedCollapsed());
  const [chatSidebarOpen, setChatSidebarOpen] = useChatSidebarOpen();
  const [workbenchMounted, setWorkbenchMounted] = useState(() => onWorkbench);

  useEffect(() => {
    if (onWorkbench) {
      setWorkbenchMounted(true);
    }
  }, [onWorkbench]);

  const persistNavCollapsed = useCallback((next: boolean) => {
    setCollapsed(next);
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
    } catch {
      /* ignore */
    }
  }, []);

  /** Mobile header / overlay: simple nav toggle. */
  const toggleCollapsed = useCallback(() => {
    persistNavCollapsed(!collapsed);
  }, [collapsed, persistNavCollapsed]);

  /**
   * Desktop nav edge, matching upstream: expanding the nav while the classic
   * history rail is closed opens both; collapsing the nav leaves history alone.
   */
  const handleNavRailToggle = useCallback(() => {
    if (collapsed) {
      persistNavCollapsed(false);
      if (!isMinimalLayout && isChatPath(currentPath) && !chatSidebarOpen) {
        setChatSidebarOpen(true);
      }
      return;
    }
    persistNavCollapsed(true);
  }, [
    collapsed,
    chatSidebarOpen,
    currentPath,
    isMinimalLayout,
    persistNavCollapsed,
    setChatSidebarOpen,
  ]);

  /**
   * History rail toggle, shared by the nav row button, the rail's own edge
   * pill and ⇧⌘B.
   *
   * Opening from anywhere else lands on /chat first: the rail only exists on
   * that route (classic layout), so toggling it from /tasks would otherwise
   * flip a boolean nobody can see.
   */
  const handleHistoryRailToggle = useCallback(() => {
    if (isMinimalLayout) return; // Minimal has one rail; history lives inside it.
    if (isChatPath(currentPath)) {
      if (chatSidebarOpen) {
        setChatSidebarOpen(false);
        return;
      }
      // MainLayout's listener also re-opens the nav when it was collapsed.
      window.dispatchEvent(new Event(EXPAND_CHAT_RAIL_EVENT));
      return;
    }
    window.dispatchEvent(new Event(EXPAND_CHAT_RAIL_EVENT));
    navigate("/chat");
  }, [
    chatSidebarOpen,
    currentPath,
    isMinimalLayout,
    navigate,
    setChatSidebarOpen,
  ]);

  useRailShortcuts({
    onToggleNav: isMobile ? toggleCollapsed : handleNavRailToggle,
    onToggleHistory: handleHistoryRailToggle,
  });

  const navEdgeLabel = t(
    collapsed ? "layout.expandNav" : "layout.collapseNav",
    collapsed ? "展开导航栏" : "收起导航栏",
  );
  const navEdgeHint = `${navEdgeLabel} (${railShortcutLabel(
    "toggle-nav",
    isMacPlatform(),
  )})`;

  // When switching to mobile, always collapse; restore saved preference on desktop
  useEffect(() => {
    if (isMobile) {
      setCollapsed(true);
    } else {
      setCollapsed(getSavedCollapsed());
    }
  }, [isMobile]);

  // Escape closes whichever mobile rail is covering the page. Desktop rails
  // stay put: there they are part of the layout, not an overlay.
  useEffect(() => {
    if (!isMobile) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      // Dialogs (and the composer's popovers) close first, on their own.
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) {
        return;
      }
      if (chatSidebarOpen && isChatPath(currentPath)) {
        setChatSidebarOpen(false);
        return;
      }
      if (!collapsed) setCollapsed(true);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [chatSidebarOpen, collapsed, currentPath, isMobile, setChatSidebarOpen]);

  // On mobile, collapse sidebar when navigating to a new page
  useEffect(() => {
    if (isMobile) {
      setCollapsed(true);
    }
  }, [currentPath, isMobile]);

  // Listen for custom event from ChatPage mobile header to toggle the global
  // navigation sidebar (since the global Header is hidden on mobile fullscreen).
  useEffect(() => {
    const handler = () => setCollapsed((prev) => !prev);
    window.addEventListener("octop:toggle-nav", handler);
    return () => window.removeEventListener("octop:toggle-nav", handler);
  }, []);

  // Chat history rail expand: if nav is also collapsed, open both rails.
  // Minimal layout has no second rail — Sidebar handles records pane itself.
  useEffect(() => {
    if (isMinimalLayout) return;
    const handler = () => {
      setChatSidebarOpen(true);
      if (collapsed) {
        persistNavCollapsed(false);
      }
    };
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, handler);
    return () => window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, handler);
  }, [collapsed, isMinimalLayout, persistNavCollapsed, setChatSidebarOpen]);

  const routes = (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        {routeConfigs.map((rc) => {
          let el = rc.useWrapper ? <ChatWithKey /> : rc.element;
          if (!rc.useWrapper && routeNeedsPermission(rc.path)) {
            el = <RequirePermission>{el}</RequirePermission>;
          }
          return <Route key={rc.path} path={rc.path} element={el} />;
        })}
      </Routes>
    </Suspense>
  );

  const isChatRoute = isChatPath(currentPath);

  useEffect(() => {
    document.documentElement.classList.toggle("octop-chat-open", isChatRoute);
    return () => {
      document.documentElement.classList.remove("octop-chat-open");
    };
  }, [isChatRoute]);

  return (
    <ServiceRestartProvider>
      <BackupOperationProvider>
        {/* Shell column: the window's title band floats over the workbench row,
            so every column paints its own surface to the top edge. */}
        <div
          className="octop-window-shell"
          style={
            {
              height: "100%",
              boxSizing: "border-box",
              /* iOS PWA landscape sides. Top is owned by Header (#664/#746),
                 bottom is handled per-surface. */
              paddingLeft: "env(safe-area-inset-left, 0px)",
              paddingRight: "env(safe-area-inset-right, 0px)",
              display: "flex",
              flexDirection: "column",
              background: isChatRoute
                ? "var(--fn-bg-elevated, #fff)"
                : "var(--fn-bg-primary)",
              transition: "background var(--fn-transition)",
              overflow: "hidden",
              position: "relative",
              /* The title row's height, for columns that paint their own
                 surface behind it (see the band below). */
              "--octop-shell-top-band": `${shellTopBand}px`,
            } as React.CSSProperties
          }
        >
          {/* macOS only: one drag strip beside the traffic lights. Windows drags
              from the caption menu row, not from the page. */}
          {shellTopBand > 0 && <DesktopWindowDragBand position="absolute" />}

          <div
            style={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "row",
              overflow: "hidden",
            }}
          >
            {/* Mobile overlay backdrop */}
            {isMobile && !collapsed && (
              <div
                onClick={toggleCollapsed}
                style={{
                  position: "fixed",
                  inset: 0,
                  background: "rgba(0, 0, 0, 0.40)",
                  zIndex: 99,
                }}
              />
            )}

            <div
              style={{
                position: "relative",
                flexShrink: 0,
                alignSelf: "stretch",
                display: "flex",
                minHeight: 0,
              }}
            >
              <Sidebar
                selectedKey={selectedKey}
                collapsed={collapsed}
                onToggle={toggleCollapsed}
                isMobile={isMobile}
              />
              {!isMobile && (
                <RailEdgeControl
                  expanded={!collapsed}
                  onToggle={handleNavRailToggle}
                  side="end"
                  placement="center"
                  label={navEdgeLabel}
                  hint={navEdgeHint}
                  shortcut={railShortcutAria("toggle-nav")}
                />
              )}
            </div>

            {isChatRoute && !isMinimalLayout && (
              <div
                id={CHAT_HISTORY_RAIL_ID}
                style={{
                  flexShrink: 0,
                  display: "flex",
                  alignSelf: "stretch",
                  minHeight: 0,
                  height: "100%",
                  position: "relative",
                }}
              />
            )}

            {/* Right column: mobile header (if any) + page content */}
            <div
              style={{
                flex: 1,
                minWidth: 0,
                minHeight: 0,
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              {isMobile &&
                !(
                  SELF_HEADER_PATHS.has(currentPath) ||
                  [...SELF_HEADER_PATHS].some((p) =>
                    currentPath.startsWith(p + "/"),
                  )
                ) && (
                  <Header
                    selectedKey={selectedKey}
                    collapsed={collapsed}
                    onToggle={toggleCollapsed}
                    isMobile={isMobile}
                  />
                )}

              <Layout
                style={{
                  background: "transparent",
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                  minWidth: 0,
                  minHeight: 0,
                }}
              >
                <Content
                  className="page-container"
                  style={{
                    background: isChatRoute
                      ? "var(--fn-bg-elevated, #fff)"
                      : "var(--fn-bg-layout)",
                    transition: "background var(--fn-transition)",
                    flex: 1,
                    overflow: "hidden",
                    display: "flex",
                    flexDirection: "column",
                    minHeight: 0,
                  }}
                >
                  <PwaAutoPrompt />

                  {workbenchMounted && (
                    <div
                      style={{
                        flex: 1,
                        minHeight: 0,
                        overflow: "hidden",
                        display: onWorkbench ? "flex" : "none",
                        flexDirection: "column",
                      }}
                    >
                      <RequirePermission>
                        <Suspense fallback={<PageLoading />}>
                          <WorkbenchPage isVisible={onWorkbench} />
                        </Suspense>
                      </RequirePermission>
                    </div>
                  )}

                  {/* Keep Routes mounted when visiting Workbench so leaving/re-entering
                  does not remount every lazy page (lag + lost UI state). */}
                  <div
                    style={{
                      flex: 1,
                      minHeight: 0,
                      overflow: "hidden",
                      display: onWorkbench ? "none" : "flex",
                      flexDirection: "column",
                    }}
                  >
                    {isFullscreen ? (
                      <div
                        style={{
                          flex: 1,
                          minHeight: 0,
                          overflow: "hidden",
                          display: "flex",
                          flexDirection: "column",
                        }}
                      >
                        {routes}
                      </div>
                    ) : (
                      <div className="page-content">{routes}</div>
                    )}
                  </div>
                </Content>
              </Layout>
            </div>
          </div>
        </div>
      </BackupOperationProvider>
    </ServiceRestartProvider>
  );
}
