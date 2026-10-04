import { lazy, Suspense, useContext, useEffect, useState } from "react";
import { SettingsBackgroundContext } from "./SettingsBackground";
import { useAgent } from "../context/AgentContext";
import { useLocation, useNavigate } from "react-router-dom";
import { useCurrentUser, useSetCurrentUser } from "../hooks/useCurrentUser";
import AvatarDropdown from "../components/AvatarDropdown";
import SidebarNavCustomizer from "../layouts/SidebarNavCustomizer";
import {
  CHAT_HISTORY_RAIL_ID,
  OPEN_NAV_RECORDS_EVENT,
  isChatPath,
} from "../layouts/chatHistoryRail";
import { EXPAND_CHAT_RAIL_EVENT } from "../pages/Chat/components/ChatSidebarPanel";
import Navigation from "./Navigation";
import SidebarFrame from "./SidebarFrame";
import HistoryHost from "./HistoryHost";
const WorkspaceDrawer = lazy(
  () => import("../pages/Agent/Workspace/components/WorkspaceDrawer"),
);
import { useWorkBuddyNavigation } from "./navigationModel";

export default function WorkBuddySidebar({
  collapsed,
  onToggle,
  isMobile = false,
}: {
  collapsed: boolean;
  onToggle: () => void;
  isMobile?: boolean;
}) {
  const user = useCurrentUser();
  const setUser = useSetCurrentUser();
  const { catalog, sections, savedLayout, setSavedLayout } =
    useWorkBuddyNavigation();
  const [customizerOpen, setCustomizerOpen] = useState(false);
  const { activeAgentId } = useAgent();
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceMounted, setWorkspaceMounted] = useState(false);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const background = useContext(SettingsBackgroundContext);
  const workspacePath =
    pathname === "/settings" || pathname.startsWith("/settings/")
      ? background?.pathname ?? "/home"
      : pathname;
  const compact = collapsed && !isMobile;
  useEffect(() => {
    const expand = () => {
      if (collapsed) onToggle();
    };
    window.addEventListener(OPEN_NAV_RECORDS_EVENT, expand);
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, expand);
    return () => {
      window.removeEventListener(OPEN_NAV_RECORDS_EVENT, expand);
      window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, expand);
    };
  }, [collapsed, onToggle]);
  const onNavigate = (path: string) => {
    if (!(path === "/chat" && pathname.startsWith("/chat/"))) navigate(path);
    if (isMobile && !collapsed) onToggle();
  };
  return (
    <SidebarFrame
      collapsed={collapsed}
      onToggle={onToggle}
      isMobile={isMobile}
      navigation={
        <Navigation
          compact={compact}
          sections={sections}
          onNavigate={onNavigate}
          filesAvailable={Boolean(activeAgentId)}
          onOpenFiles={() => {
            setWorkspaceMounted(true);
            setWorkspaceOpen(true);
            if (isMobile && !collapsed) onToggle();
          }}
        />
      }
      history={
        <div id={CHAT_HISTORY_RAIL_ID}>
          {!isChatPath(workspacePath) ? <HistoryHost /> : null}
        </div>
      }
      footer={
        <AvatarDropdown
          user={user}
          onUserChange={setUser}
          placement="sidebar"
          compact={compact}
          onBeforeOpenSettings={isMobile && !collapsed ? onToggle : undefined}
          onCustomizeNav={() => setCustomizerOpen(true)}
        />
      }
    >
      <SidebarNavCustomizer
        open={customizerOpen}
        catalog={catalog}
        layout={savedLayout}
        onClose={() => setCustomizerOpen(false)}
        onSaved={setSavedLayout}
      />
      {workspaceMounted && activeAgentId && (
        <Suspense fallback={null}>
          <WorkspaceDrawer
            agentId={activeAgentId}
            open={workspaceOpen}
            onClose={() => setWorkspaceOpen(false)}
          />
        </Suspense>
      )}
    </SidebarFrame>
  );
}
