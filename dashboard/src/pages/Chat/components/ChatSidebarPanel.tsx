import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { RefObject } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import cx from "classnames";
import SessionList from "./SessionList";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";
import type { Session } from "../hooks/useSessions";
import type { OctopAgent } from "../../../context/AgentContext";
import RailEdgeControl from "../../../components/RailEdgeControl";
import {
  isMacPlatform,
  railShortcutAria,
  railShortcutLabel,
} from "../../../utils/railShortcuts";
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
  /** Owned experts that cannot chat yet — see ``SessionList.unreadyExperts``. */
  unreadyExperts?: number;
  sessions: Session[];
  activeThreadId: string | null;
  resolvedAgentId: string | null | undefined;
  sessionsHasMore: boolean;
  sessionsLoadingMore: boolean;
  onLoadMoreSessions: () => void;
  onFetchAllSessions: () => void;
  onSelectSession: (sessionId: string, agentId: string) => void;
  onAgentSelect: (agentId: string) => void;
  /** Start a fresh chat from an expert row (classic + minimal). */
  onNewChatWithAgent: (agentId: string) => void;
  onDeleteSession: (
    id: string,
    compact: boolean,
  ) => void | Promise<boolean | null | void>;
  onRenameSession: (id: string, name: string) => void;
  onPinSession: (id: string, pinned: boolean) => void;
  onForkSession: (id: string, agentId?: string | null) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
  onSidebarOpenChange: (open: boolean) => void;
  onSidebarResizeStart: (e: React.PointerEvent) => void;
  /** Mounted in MainLayout left rail (between app nav and content). */
  layoutRail?: boolean;
  /**
   * Minimal layout: render SessionList only inside the nav "records" pane
   * (no second rail chrome / mobile overlay).
   */
  navEmbedded?: boolean;
}

export default function ChatSidebarPanel({
  isMobile,
  sidebarOpen,
  sidebarWidth,
  isSidebarResizing = false,
  sidebarElRef,
  agents,
  unreadyExperts,
  sessions,
  activeThreadId,
  resolvedAgentId,
  sessionsHasMore,
  sessionsLoadingMore,
  onLoadMoreSessions,
  onFetchAllSessions,
  onSelectSession,
  onAgentSelect,
  onNewChatWithAgent,
  onDeleteSession,
  onRenameSession,
  onPinSession,
  onForkSession,
  forkDisabled,
  forkDisabledHint,
  onSidebarOpenChange,
  onSidebarResizeStart,
  layoutRail = false,
  navEmbedded = false,
}: ChatSidebarPanelProps) {
  const { t } = useTranslation();

  const historyLabel = sidebarOpen
    ? t("chat.collapseHistorySidebar", "收起对话历史")
    : t("chat.expandHistorySidebar", "展开对话历史");
  /** Tooltip carries the accelerator; the accessible name stays the action. */
  const historyHint = `${historyLabel} (${railShortcutLabel(
    "toggle-history",
    isMacPlatform(),
  )})`;

  const handleRailToggle = useCallback(() => {
    if (sidebarOpen) {
      onSidebarOpenChange(false);
      return;
    }
    // MainLayout may also expand the nav when both rails were collapsed.
    window.dispatchEvent(new Event(EXPAND_CHAT_RAIL_EVENT));
    onSidebarOpenChange(true);
  }, [sidebarOpen, onSidebarOpenChange]);

  /**
   * The rail collapses from its own header, next to the search field, the way
   * every comparable app does it. It used to hang inside the nav's "对话" item,
   * one row under the nav's own collapse button and with the same glyph — two
   * identical panel icons stacked, and neither said which panel it closed.
   */
  const railToggle =
    !isMobile && !navEmbedded ? (
      <button
        type="button"
        className={styles.railHeaderToggle}
        onClick={handleRailToggle}
        aria-label={historyLabel}
        aria-expanded={sidebarOpen}
        aria-keyshortcuts={railShortcutAria("toggle-history")}
        title={historyHint}
      >
        {sidebarOpen ? (
          <PanelLeftClose size={16} strokeWidth={1.8} aria-hidden />
        ) : (
          <PanelLeftOpen size={16} strokeWidth={1.8} aria-hidden />
        )}
      </button>
    ) : null;

  const sessionList = navEmbedded ? (
    <MinimalAgentSessionNav
      agents={agents}
      activeId={activeThreadId}
      activeAgentId={resolvedAgentId ?? null}
      activeSessions={sessions}
      onSelect={onSelectSession}
      onAgentSelect={onAgentSelect}
      onNewChat={onNewChatWithAgent}
      onDeleteActive={onDeleteSession}
      onRenameActive={onRenameSession}
      onPinActive={onPinSession}
      onFork={onForkSession}
      activeForkDisabled={forkDisabled}
      activeForkDisabledHint={forkDisabledHint}
    />
  ) : (
    <SessionList
      agents={agents}
      unreadyExperts={unreadyExperts}
      railToggle={railToggle}
      sessions={sessions}
      activeId={activeThreadId}
      activeAgentId={resolvedAgentId ?? null}
      hasMore={sessionsHasMore}
      loadingMore={sessionsLoadingMore}
      onLoadMore={onLoadMoreSessions}
      onFetchAllSessions={onFetchAllSessions}
      onSelect={onSelectSession}
      onAgentSelect={onAgentSelect}
      onNewChat={onNewChatWithAgent}
      onDelete={onDeleteSession}
      onRename={onRenameSession}
      onPin={onPinSession}
      onFork={onForkSession}
      activeForkDisabled={forkDisabled}
      activeForkDisabledHint={forkDisabledHint}
    />
  );

  if (navEmbedded) {
    return (
      <div className={styles.sidebarNavEmbedded} data-testid="chat-nav-records">
        {sessionList}
      </div>
    );
  }

  return (
    <div
      className={cx(
        styles.sidebarWrapper,
        layoutRail && styles.sidebarWrapperLayoutRail,
        !isMobile && !sidebarOpen && styles.sidebarWrapperCollapsed,
      )}
    >
      {isMobile && sidebarOpen && (
        <div
          className={styles.overlay}
          onClick={() => onSidebarOpenChange(false)}
        />
      )}

      <div
        ref={sidebarElRef}
        className={cx(
          styles.sidebar,
          sidebarOpen && styles.sidebarOpen,
          isSidebarResizing && styles.sidebarResizing,
        )}
        style={
          !isMobile && sidebarOpen
            ? { width: sidebarWidth, minWidth: sidebarWidth }
            : undefined
        }
      >
        {sessionList}
        {!isMobile && sidebarOpen && (
          <div
            className={cx(
              styles.sidebarResizeHandle,
              isSidebarResizing && styles.sidebarResizeHandleActive,
            )}
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
          persistent={!sidebarOpen}
          onToggle={handleRailToggle}
          side={sidebarOpen ? "end" : "start"}
          /* Collapsed: share the nav rail divider — avoid a second gapped line. */
          showLine={sidebarOpen}
          /* One pill on this seam, always straddling it. It used to shift to
             `after` when collapsed, which put it 3px away from the nav rail's
             own pill and made the pair unreadable. */
          placement="center"
          passThrough={sidebarOpen}
          label={historyLabel}
          hint={historyHint}
          className={
            sidebarOpen ? styles.chatRailEdgeOpen : styles.chatRailEdgeClosed
          }
        />
      )}
    </div>
  );
}
