import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { RefObject } from "react";
import SessionList from "./SessionList";
import type { Session } from "../hooks/useSessions";
import type { OctopAgent } from "../../../context/AgentContext";
import RailEdgeControl from "../../../components/RailEdgeControl";
import styles from "../index.module.less";

/** Dispatched when the chat history rail expand control is clicked. */
export const EXPAND_CHAT_RAIL_EVENT = "octop:expand-chat-rail";

interface ChatSidebarPanelProps {
  isMobile: boolean;
  sidebarOpen: boolean;
  sidebarWidth: number;
  isSidebarResizing?: boolean;
  sidebarElRef?: RefObject<HTMLDivElement>;
  agents: OctopAgent[];
  sessions: Session[];
  activeThreadId: string | null;
  resolvedAgentId: string | null | undefined;
  sessionsHasMore: boolean;
  sessionsLoadingMore: boolean;
  onLoadMoreSessions: () => void;
  onFetchAllSessions: () => void;
  onSelectSession: (sessionId: string, agentId: string) => void;
  onAgentSelect: (agentId: string) => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, name: string) => void;
  onPinSession: (id: string, pinned: boolean) => void;
  onForkSession: (id: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
  onSidebarOpenChange: (open: boolean) => void;
  onSidebarResizeStart: (e: React.PointerEvent) => void;
  /** Mounted in MainLayout left rail (between app nav and content). */
  layoutRail?: boolean;
}

export default function ChatSidebarPanel({
  isMobile,
  sidebarOpen,
  sidebarWidth,
  isSidebarResizing = false,
  sidebarElRef,
  agents,
  sessions,
  activeThreadId,
  resolvedAgentId,
  sessionsHasMore,
  sessionsLoadingMore,
  onLoadMoreSessions,
  onFetchAllSessions,
  onSelectSession,
  onAgentSelect,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onForkSession,
  forkDisabled,
  forkDisabledHint,
  onSidebarOpenChange,
  onSidebarResizeStart,
  layoutRail = false,
}: ChatSidebarPanelProps) {
  const { t } = useTranslation();

  const handleRailToggle = useCallback(() => {
    if (sidebarOpen) {
      onSidebarOpenChange(false);
      return;
    }
    // MainLayout may also expand the nav when both rails were collapsed.
    window.dispatchEvent(new Event(EXPAND_CHAT_RAIL_EVENT));
    onSidebarOpenChange(true);
  }, [sidebarOpen, onSidebarOpenChange]);

  return (
    <div
      className={`${styles.sidebarWrapper} ${
        layoutRail ? styles.sidebarWrapperLayoutRail : ""
      } ${!isMobile && !sidebarOpen ? styles.sidebarWrapperCollapsed : ""}`}
    >
      {isMobile && sidebarOpen && (
        <div
          className={styles.overlay}
          onClick={() => onSidebarOpenChange(false)}
        />
      )}

      <div
        ref={sidebarElRef}
        className={`${styles.sidebar} ${
          sidebarOpen ? styles.sidebarOpen : ""
        } ${isSidebarResizing ? styles.sidebarResizing : ""}`}
        style={
          !isMobile && sidebarOpen
            ? { width: sidebarWidth, minWidth: sidebarWidth }
            : undefined
        }
      >
        <SessionList
          agents={agents}
          sessions={sessions}
          activeId={activeThreadId}
          activeAgentId={resolvedAgentId ?? null}
          hasMore={sessionsHasMore}
          loadingMore={sessionsLoadingMore}
          onLoadMore={onLoadMoreSessions}
          onFetchAllSessions={onFetchAllSessions}
          onSelect={onSelectSession}
          onAgentSelect={onAgentSelect}
          onDelete={onDeleteSession}
          onRename={onRenameSession}
          onPin={onPinSession}
          onFork={onForkSession}
          activeForkDisabled={forkDisabled}
          activeForkDisabledHint={forkDisabledHint}
        />
        {!isMobile && sidebarOpen && (
          <div
            className={`${styles.sidebarResizeHandle} ${
              isSidebarResizing ? styles.sidebarResizeHandleActive : ""
            }`}
            onPointerDown={onSidebarResizeStart}
            role="separator"
            aria-orientation="vertical"
            aria-label={t("chat.resizeSidebar", "调整侧栏宽度")}
          />
        )}
      </div>

      {!isMobile && (
        <RailEdgeControl
          expanded={sidebarOpen}
          onToggle={handleRailToggle}
          side={sidebarOpen ? "end" : "start"}
          /* Collapsed: share the nav rail divider — avoid a second gapped line. */
          showLine={sidebarOpen}
          className={
            sidebarOpen ? styles.chatRailEdgeOpen : styles.chatRailEdgeClosed
          }
        />
      )}
    </div>
  );
}
