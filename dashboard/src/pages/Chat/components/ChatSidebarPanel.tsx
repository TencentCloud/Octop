import { useTranslation } from "react-i18next";
import type { RefObject } from "react";
import SessionList from "./SessionList";
import type { Session } from "../hooks/useSessions";
import type { OctopAgent } from "../../../context/AgentContext";
import styles from "../index.module.less";

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
  onSidebarOpenChange,
  onSidebarResizeStart,
  layoutRail = false,
}: ChatSidebarPanelProps) {
  const { t } = useTranslation();

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
    </div>
  );
}
