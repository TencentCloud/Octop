import { Layout, Spin } from "antd";
import { lazy, Suspense, useEffect, useState, useCallback } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import Sidebar from "../Sidebar";
import Header from "../Header";
import { ServiceRestartProvider } from "../../context/ServiceRestartContext";
import PwaUpdatePrompt from "../../components/PwaUpdatePrompt";
import { PwaAutoPrompt } from "../../components/PwaInstallPrompt";
import {
  routeConfigs,
  resolveSelectedKey,
  FULLSCREEN_PATHS,
  MOBILE_FULLSCREEN_PATHS,
  SELF_HEADER_PATHS,
} from "../../routes";
import { CHAT_HISTORY_RAIL_ID, isChatPath } from "../chatHistoryRail";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useChatSidebarOpen } from "../../pages/Chat/hooks/useChatSidebarState";
import RequireAdmin from "../../components/RequireAdmin";

const Chat = lazy(() => import("../../pages/Chat"));
const TerminalPage = lazy(() => import("../../pages/Control/Terminal"));

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
  const currentPath = location.pathname;
  const selectedKey = resolveSelectedKey(currentPath);
  const isMobile = useIsMobile();
  const isFullscreen =
    FULLSCREEN_PATHS.has(currentPath) ||
    [...FULLSCREEN_PATHS].some((p) => currentPath.startsWith(p + "/")) ||
    (isMobile && MOBILE_FULLSCREEN_PATHS.has(currentPath));

  const [collapsed, setCollapsed] = useState(() => getSavedCollapsed());
  const [chatSidebarOpen, setChatSidebarOpen] = useChatSidebarOpen();
  const [terminalMounted, setTerminalMounted] = useState(
    () => currentPath === "/terminal",
  );

  useEffect(() => {
    if (currentPath === "/terminal") {
      setTerminalMounted(true);
    }
  }, [currentPath]);

  const toggleCollapsed = useCallback(() => {
    if (!isMobile && isChatPath(currentPath)) {
      if (!collapsed && chatSidebarOpen) {
        setChatSidebarOpen(false);
        return;
      }
      if (collapsed) {
        setChatSidebarOpen(true);
      }
    }

    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [chatSidebarOpen, collapsed, currentPath, isMobile, setChatSidebarOpen]);

  // When switching to mobile, always collapse; restore saved preference on desktop
  useEffect(() => {
    if (isMobile) {
      setCollapsed(true);
    } else {
      setCollapsed(getSavedCollapsed());
    }
  }, [isMobile]);

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

  const routes = (
    <Suspense
      fallback={
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            flex: 1,
          }}
        >
          <Spin size="large" />
        </div>
      }
    >
      <Routes>
        {routeConfigs.map((rc) => {
          let el = rc.useWrapper ? <ChatWithKey /> : rc.element;
          if (rc.path.startsWith("/admin/")) {
            el = <RequireAdmin>{el}</RequireAdmin>;
          }
          return <Route key={rc.path} path={rc.path} element={el} />;
        })}
      </Routes>
    </Suspense>
  );

  const isChatRoute = isChatPath(currentPath);

  return (
    <ServiceRestartProvider>
      <div
        style={{
          height: "100dvh",
          display: "flex",
          flexDirection: "row",
          background: "var(--fn-bg-layout)",
          transition: "background var(--fn-transition)",
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

        <Sidebar
          selectedKey={selectedKey}
          collapsed={collapsed}
          onToggle={toggleCollapsed}
          isMobile={isMobile}
        />

        {isChatRoute && (
          <div
            id={CHAT_HISTORY_RAIL_ID}
            style={{
              flexShrink: 0,
              display: "flex",
              alignSelf: "stretch",
              minHeight: 0,
              height: "100%",
            }}
          />
        )}

        {/* Right column: header on top, page content below */}
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
          {!(
            isMobile &&
            (SELF_HEADER_PATHS.has(currentPath) ||
              [...SELF_HEADER_PATHS].some((p) =>
                currentPath.startsWith(p + "/"),
              ))
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
                background: "var(--fn-bg-layout)",
                transition: "background var(--fn-transition)",
                flex: 1,
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
                minHeight: 0,
              }}
            >
              <PwaUpdatePrompt />
              <PwaAutoPrompt />

              {terminalMounted && (
                <div
                  style={{
                    flex: 1,
                    minHeight: 0,
                    overflow: "hidden",
                    display: currentPath === "/terminal" ? "flex" : "none",
                    flexDirection: "column",
                  }}
                >
                  <Suspense
                    fallback={
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "center",
                          alignItems: "center",
                          flex: 1,
                        }}
                      >
                        <Spin size="large" />
                      </div>
                    }
                  >
                    <TerminalPage isVisible={currentPath === "/terminal"} />
                  </Suspense>
                </div>
              )}

              {currentPath !== "/terminal" &&
                (isFullscreen ? (
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
                ))}
            </Content>
          </Layout>
        </div>
      </div>
    </ServiceRestartProvider>
  );
}
