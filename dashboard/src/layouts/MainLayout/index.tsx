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
import { EXPAND_CHAT_RAIL_EVENT } from "../../pages/Chat/components/ChatSidebarPanel";
import RequirePermission from "../../components/RequirePermission";
import { routeNeedsPermission } from "../../utils/permissions";
import { useLayoutMode } from "../../context/LayoutModeContext";
import { useDashboardPushToast } from "../../hooks/useDashboardPushToast";
import { useDesktopChromeStyle } from "../../hooks/useDesktopChrome";
import { useWindowFullscreen } from "../../hooks/useWindowFullscreen";
import { useRailShortcuts } from "../../hooks/useRailShortcuts";
import {
  chromeTopBandPx,
  windowControlsInset,
  DESKTOP_DRAG_REGION_CLASS,
} from "../../utils/desktopChrome";

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
  const desktopChrome = useDesktopChromeStyle();
  const windowFullscreen = useWindowFullscreen();
  /**
   * The shell's title row, owned by the layout rather than by any one column:
   * 32px of draggable space that also keeps the native buttons from covering
   * page chrome. Zero in the browser, on Linux (system frame), and in full
   * screen (no buttons to make room for).
   */
  const shellTopBand = isMobile
    ? 0
    : chromeTopBandPx(desktopChrome, windowFullscreen);

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

  /**
   * Nav rail toggle — the brand-row button and ⌘B.
   *
   * One control, one effect: it moves the nav rail and nothing else. It used to
   * also pop the history rail open when expanding on a chat route, which made
   * one keystroke change two panels; with the history rail's own button and
   * ⇧⌘B in place, that surprise is no longer load-bearing.
   */
  const toggleCollapsed = useCallback(() => {
    persistNavCollapsed(!collapsed);
  }, [collapsed, persistNavCollapsed]);

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
    onToggleNav: toggleCollapsed,
    onToggleHistory: handleHistoryRailToggle,
  });

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
        {/* Shell column: the window's own title row on top, the workbench row
            beneath it. */}
        <div
          style={{
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
          }}
        >
          {/* One continuous drag handle across the window, reserving the band
              the native buttons live in (macOS traffic lights at the start,
              Windows caption buttons at the end). Rendering it here — instead
              of letting each column reserve its own slice — is what makes the
              top row unbroken from the sidebar to the page. */}
          {shellTopBand > 0 && (
            <div
              aria-hidden
              className={DESKTOP_DRAG_REGION_CLASS}
              style={{
                height: shellTopBand,
                flexShrink: 0,
                /* Keep the drag region out from under the Windows caption
                   buttons, which are drawn over this same band. */
                marginInlineEnd: windowControlsInset(desktopChrome, "end"),
              }}
            />
          )}

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
              {/* The rail's own header carries the collapse control (it used to
                  be a hover-only pill on this seam, which nobody could find and
                  which collided with the history rail's pill next door). */}
              <Sidebar
                selectedKey={selectedKey}
                collapsed={collapsed}
                onToggle={toggleCollapsed}
                isMobile={isMobile}
              />
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
