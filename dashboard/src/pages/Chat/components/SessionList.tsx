import {
  Fragment,
  memo,
  useCallback,
  useMemo,
  useState,
  useRef,
  useEffect,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import {
  Pencil,
  MoreHorizontal,
  Trash2,
  Pin,
  PinOff,
  MessageSquarePlus,
  Search,
  GitFork,
  Eye,
  EyeOff,
  RefreshCw,
} from "lucide-react";
import type { Session } from "../hooks/useSessions";
import type { InboxByAgent } from "../hooks/useSessionInbox";
import type { OctopAgent } from "../../../context/AgentContext";
import { isAgentChatReady } from "../../../utils/agentError";
import { showConfirmModal } from "../../../utils/confirmModal";
import { ExpertIcon } from "../../Experts/components/iconForName";
import { useHiddenSharedExperts } from "../hooks/useHiddenSharedExperts";
import SessionChannelIcon from "./SessionChannelIcon";
import SharedExpertHint from "./SharedExpertHint";
import TeamChatBadge from "./TeamChatBadge";
import SessionGroupHeader from "./SessionGroupHeader";
import styles from "../index.module.less";

function AgentUnreadBadge({ count }: { count: number }) {
  const { t } = useTranslation();
  if (!count || count <= 0) return null;
  return (
    <span
      className={styles.agentUnreadBadge}
      aria-label={t("chat.unreadMessages", "未读消息")}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

/** Session count marker on an agent row (PLAN §8.2: ``▸ n``). */
function SessionCountMark({ count }: { count: number }) {
  if (!count || count <= 0) return null;
  return (
    <span
      style={{
        flexShrink: 0,
        fontSize: 12,
        color: "var(--fn-text-tertiary)",
      }}
    >
      ▸ {count}
    </span>
  );
}

/**
 * 「项目会话」marker. Renders on session rows only — the agent row carries the
 * team badge (S-4: 群聊 → 项目会话, on separate rows, fixed order).
 * Definition (S-11): only sessions produced by project-task dispatch.
 */
function ProjectSessionBadge() {
  const { t } = useTranslation();
  const label = t("chat.projectSessionBadge");
  return (
    <span className={styles.sharedExpertFlag} aria-label={label}>
      {label}
    </span>
  );
}

interface SessionProjectGroup {
  projectId: string | null;
  projectName: string | null;
  sessions: Session[];
}

/**
 * Group rendered session rows by project: project chats first (projectName
 * asc, then projectId asc), non-project chats keep their incoming time order.
 * Project fields come from the API only — never re-derived here (T2.6).
 */
function groupSessionsByProject(sessions: Session[]): SessionProjectGroup[] {
  const byProject = new Map<string, SessionProjectGroup>();
  const noProject: Session[] = [];
  for (const session of sessions) {
    if (session.projectId == null) {
      noProject.push(session);
      continue;
    }
    const existing = byProject.get(session.projectId);
    if (existing) {
      existing.sessions.push(session);
    } else {
      byProject.set(session.projectId, {
        projectId: session.projectId,
        projectName: session.projectName ?? null,
        sessions: [session],
      });
    }
  }
  const groups = [...byProject.values()].sort((a, b) => {
    const an = a.projectName ?? "";
    const bn = b.projectName ?? "";
    if (an !== bn) return an.localeCompare(bn);
    return (a.projectId ?? "").localeCompare(b.projectId ?? "");
  });
  if (noProject.length > 0) {
    groups.push({ projectId: null, projectName: null, sessions: noProject });
  }
  return groups;
}

interface SessionManageHandlers {
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
}

interface SessionItemProps {
  session: Session;
  isActive: boolean;
  onSelect: (id: string) => void;
  /**
   * Row management is agent-scoped, so the 📌 pinned section omits the menu for
   * sessions owned by another agent (a click still switches to that session).
   */
  onDelete?: (id: string) => void;
  onRename?: (id: string, name: string) => void;
  onPin?: (id: string, pinned: boolean) => void;
  onFork?: (id: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
}

const SessionItem = memo(function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
  onRename,
  onPin,
  onFork,
  forkDisabled,
  forkDisabledHint,
}: SessionItemProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(session.name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isEditing) setEditValue(session.name);
  }, [session.name, isEditing]);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== session.name) {
      onRename?.(session.id, trimmed);
    } else {
      setEditValue(session.name);
    }
    setIsEditing(false);
  }, [editValue, session.name, session.id, onRename]);

  const itemForkDisabled = Boolean(forkDisabled) || !session.hasActivity;
  const itemForkHint = !session.hasActivity
    ? t("chat.forkNoAssistant")
    : forkDisabledHint;

  const manage: SessionManageHandlers | null =
    onDelete && onRename && onPin && onFork
      ? { onDelete, onRename, onPin, onFork }
      : null;

  const menuItems: MenuProps["items"] = manage
    ? [
        {
          key: "pin",
          label: session.pinned
            ? t("chat.unpin", "取消置顶")
            : t("chat.pin", "置顶"),
          icon: session.pinned ? <PinOff size={14} /> : <Pin size={14} />,
          onClick: ({ domEvent }) => {
            domEvent.stopPropagation();
            manage.onPin(session.id, !session.pinned);
          },
        },
        {
          key: "fork",
          label: t("chat.fork", "分叉"),
          icon: <GitFork size={14} />,
          disabled: itemForkDisabled,
          title: itemForkDisabled && itemForkHint ? itemForkHint : undefined,
          onClick: ({ domEvent }) => {
            domEvent.stopPropagation();
            manage.onFork(session.id);
          },
        },
        {
          key: "rename",
          label: t("common.rename"),
          icon: <Pencil size={14} />,
          onClick: ({ domEvent }) => {
            domEvent.stopPropagation();
            setIsEditing(true);
          },
        },
        {
          key: "delete",
          label: t("common.delete", "Delete"),
          icon: <Trash2 size={14} />,
          danger: true,
          onClick: ({ domEvent }) => {
            domEvent.stopPropagation();
            showConfirmModal({
              title: t("chat.deleteSessionConfirm"),
              okText: t("common.delete"),
              cancelText: t("common.cancel"),
              okButtonProps: { danger: true },
              onOk: () => {
                manage.onDelete(session.id);
              },
            });
          },
        },
      ]
    : [];

  return (
    <div
      className={`${styles.sessionRow} ${
        isActive ? styles.sessionRowActive : ""
      } ${session.pinned ? styles.sessionRowPinned : ""}`}
      onClick={() => {
        if (!isEditing) onSelect(session.id);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !isEditing) onSelect(session.id);
      }}
    >
      <SessionChannelIcon
        channelType={session.channelType}
        size={12}
        className={styles.sessionRowIcon}
      />
      {isEditing ? (
        <input
          ref={inputRef}
          className={styles.sessionNameInput}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitEdit();
            if (e.key === "Escape") {
              setEditValue(session.name);
              setIsEditing(false);
            }
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <>
          <span className={styles.sessionRowTitle}>{session.name}</span>
          {session.projectId != null ? <ProjectSessionBadge /> : null}
          {session.pinned ? (
            <span
              className={styles.sessionRowPinIndicator}
              title={t("chat.unpin")}
            >
              <Pin size={12} strokeWidth={2} />
            </span>
          ) : null}
          {manage ? (
            <Dropdown
              menu={{ items: menuItems }}
              trigger={["click"]}
              placement="bottomRight"
            >
              <button
                type="button"
                className={styles.sessionRowMore}
                aria-label={t("common.more", "More")}
                onClick={(e) => e.stopPropagation()}
              >
                <MoreHorizontal size={15} />
              </button>
            </Dropdown>
          ) : null}
        </>
      )}
    </div>
  );
});

interface AgentCardProps {
  agent: OctopAgent;
  sessions: Session[];
  sessionCount: number;
  activeId: string | null;
  searchQuery: string;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onFetchAllSessions: () => void;
  onSelect: (sessionId: string, agentId: string) => void;
  onNewChat: (agentId: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
  activeForkDisabled?: boolean;
  activeForkDisabledHint?: string;
  onHide?: () => void;
}

function ActiveAgentCard({
  agent,
  sessions,
  sessionCount,
  activeId,
  searchQuery,
  hasMore,
  loadingMore,
  onLoadMore,
  onFetchAllSessions,
  onSelect,
  onNewChat,
  onDelete,
  onRename,
  onPin,
  onFork,
  activeForkDisabled,
  activeForkDisabledHint,
  onHide,
}: AgentCardProps) {
  const { t } = useTranslation();
  const accent = agent.color || "#6366f1";

  const filteredSessions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.name.toLowerCase().includes(q));
  }, [sessions, searchQuery]);

  const sessionGroups = useMemo(
    () => groupSessionsByProject(filteredSessions),
    [filteredSessions],
  );

  const fetchAllRequestedRef = useRef(false);
  useEffect(() => {
    const searching = Boolean(searchQuery.trim());
    if (!searching) {
      fetchAllRequestedRef.current = false;
      return;
    }
    if (fetchAllRequestedRef.current) return;
    fetchAllRequestedRef.current = true;
    onFetchAllSessions();
  }, [searchQuery, onFetchAllSessions]);

  const showExpandMore = hasMore && !searchQuery.trim();
  const sessionsEnabled = isAgentChatReady(agent.state);

  return (
    <div
      className={styles.agentCardActive}
      style={{
        background: `${accent}08`,
        borderColor: `${accent}18`,
      }}
    >
      <div className={styles.agentCardProfile}>
        <div
          className={styles.agentCardAvatar}
          style={{
            color: accent,
            background: `${accent}14`,
            boxShadow: `0 0 0 1px ${accent}22`,
          }}
        >
          <ExpertIcon
            iconUrl={agent.icon_url}
            iconName={agent.icon_name}
            size={16}
          />
        </div>
        <div className={styles.agentCardInfo}>
          <div className={styles.agentCardNameRow}>
            <div className={styles.agentNameCluster}>
              <div className={styles.agentCardName}>{agent.name}</div>
              <TeamChatBadge agent={agent} />
              <SharedExpertHint agent={agent} />
            </div>
            <SessionCountMark count={sessionCount} />
            <AgentUnreadBadge count={agent.unread_count ?? 0} />
            <button
              type="button"
              className={styles.agentNewChatBtn}
              aria-label={t("chatWelcome.newChat")}
              title={t("chatWelcome.newChat")}
              onClick={(e) => {
                e.stopPropagation();
                onNewChat(agent.agent_id);
              }}
            >
              <MessageSquarePlus size={14} strokeWidth={1.75} aria-hidden />
            </button>
            {onHide ? (
              <button
                type="button"
                className={styles.agentHideBtn}
                aria-label={t("chat.expertHide")}
                title={t("chat.expertHide")}
                onClick={(e) => {
                  e.stopPropagation();
                  onHide();
                }}
              >
                <EyeOff size={14} aria-hidden />
              </button>
            ) : null}
          </div>
          {agent.description ? (
            <div className={styles.agentCardDesc}>{agent.description}</div>
          ) : (
            <div className={styles.agentCardDescMuted}>
              {t("chat.agentNoDescription", "暂无描述")}
            </div>
          )}
        </div>
      </div>

      <div className={styles.agentCardSessions}>
        {!sessionsEnabled ? (
          <div className={styles.agentCardSessionsEmpty}>
            {t("chat.agentNotRunningHint")}
          </div>
        ) : sessions.length === 0 ? (
          <div className={styles.agentCardSessionsEmpty}>
            {t("chat.noSessionsYet", "直接发消息即可开始对话")}
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className={styles.agentCardSessionsEmpty}>
            {t("chat.noSearchResults", "没有匹配的会话")}
          </div>
        ) : (
          <>
            {sessionGroups.map((group) => (
              <Fragment key={group.projectId ?? "__no_project__"}>
                {group.projectId != null && group.projectName ? (
                  <SessionGroupHeader
                    nested
                    title={group.projectName}
                    count={group.sessions.length}
                  />
                ) : null}
                {group.sessions.map((s) => (
                  <SessionItem
                    key={s.id}
                    session={s}
                    isActive={activeId === s.id}
                    onSelect={(id) => onSelect(id, agent.agent_id)}
                    onDelete={onDelete}
                    onRename={onRename}
                    onPin={onPin}
                    onFork={onFork}
                    forkDisabled={
                      activeId === s.id ? activeForkDisabled : undefined
                    }
                    forkDisabledHint={
                      activeId === s.id ? activeForkDisabledHint : undefined
                    }
                  />
                ))}
              </Fragment>
            ))}
            {showExpandMore ? (
              <button
                type="button"
                className={styles.sessionLoadMore}
                onClick={onLoadMore}
                disabled={loadingMore}
              >
                {loadingMore
                  ? t("common.loading")
                  : t("chat.expandMore", "展开更多")}
              </button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

interface AgentRowProps {
  agent: OctopAgent;
  sessionCount?: number;
  onSelect: () => void;
  onNewChat?: () => void;
  onHide?: () => void;
  onUnhide?: () => void;
}

function InactiveAgentRow({
  agent,
  sessionCount = 0,
  onSelect,
  onNewChat,
  onHide,
  onUnhide,
}: AgentRowProps) {
  const { t } = useTranslation();
  const accent = agent.color || "#6366f1";

  return (
    <div className={styles.agentRowWrap}>
      <div
        className={styles.agentRow}
        onClick={onSelect}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect();
          }
        }}
      >
        <div
          className={styles.agentRowAvatar}
          style={{ color: accent, background: `${accent}12` }}
        >
          <ExpertIcon
            iconUrl={agent.icon_url}
            iconName={agent.icon_name}
            size={14}
          />
        </div>
        <div className={styles.agentRowInfo}>
          <div className={styles.agentRowNameRow}>
            <div className={styles.agentNameCluster}>
              <div className={styles.agentRowName}>{agent.name}</div>
              <TeamChatBadge agent={agent} />
              <SharedExpertHint agent={agent} />
            </div>
            <SessionCountMark count={sessionCount} />
            <AgentUnreadBadge count={agent.unread_count ?? 0} />
            {onNewChat ? (
              <button
                type="button"
                className={styles.agentNewChatBtn}
                aria-label={t("chatWelcome.newChat")}
                title={t("chatWelcome.newChat")}
                onClick={(e) => {
                  e.stopPropagation();
                  onNewChat();
                }}
              >
                <MessageSquarePlus size={14} strokeWidth={1.75} aria-hidden />
              </button>
            ) : null}
          </div>
          <div className={styles.agentRowDesc}>{agent.description || "—"}</div>
        </div>
      </div>
      {onHide ? (
        <button
          type="button"
          className={styles.agentHideBtn}
          aria-label={t("chat.expertHide")}
          title={t("chat.expertHide")}
          onClick={onHide}
        >
          <EyeOff size={14} aria-hidden />
        </button>
      ) : null}
      {onUnhide ? (
        <button
          type="button"
          className={styles.agentHideBtn}
          aria-label={t("chat.expertUnhide")}
          title={t("chat.expertUnhide")}
          onClick={onUnhide}
        >
          <Eye size={14} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

interface SessionListProps {
  agents: OctopAgent[];
  sessions: Session[];
  activeId: string | null;
  activeAgentId: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  /** Inbox snapshot: the only input for section assignment (PLAN §6). */
  inboxByAgent: InboxByAgent;
  /** Cross-agent pinned rows — the 📌 section data source (PLAN §8.1). */
  pinnedSessions: Session[];
  onLoadMore: () => void;
  onFetchAllSessions: () => void;
  /** User-triggered inbox refresh (S-10); never called implicitly. */
  onRefreshInbox: () => void;
  onSelect: (sessionId: string, agentId: string) => void;
  onAgentSelect: (agentId: string) => void;
  onNewChat: (agentId: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
  activeForkDisabled?: boolean;
  activeForkDisabledHint?: string;
}

export default function SessionList({
  agents,
  sessions,
  activeId,
  activeAgentId,
  hasMore,
  loadingMore,
  inboxByAgent,
  pinnedSessions,
  onLoadMore,
  onFetchAllSessions,
  onRefreshInbox,
  onSelect,
  onAgentSelect,
  onNewChat,
  onDelete,
  onRename,
  onPin,
  onFork,
  activeForkDisabled,
  activeForkDisabledHint,
}: SessionListProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [showingHidden, setShowingHidden] = useState(false);
  /** 📦 collapse state only — search force-expansion never writes back (S-2). */
  const [unusedExpanded, setUnusedExpanded] = useState(false);
  const { filterVisible, pickHidden, hide, unhide, canHide, isHidden } =
    useHiddenSharedExperts();

  const hiddenAgents = useMemo(
    () => [...pickHidden(agents)].sort((a, b) => b.id - a.id),
    [agents, pickHidden],
  );

  const sortedAgents = useMemo(() => {
    const visible = filterVisible(agents, {
      keepAgentIds: activeAgentId ? [activeAgentId] : [],
    });
    return [...visible].sort((a, b) => b.id - a.id);
  }, [agents, filterVisible, activeAgentId]);

  // Leave the hidden-only view once nothing remains hidden.
  const viewingHidden = showingHidden && hiddenAgents.length > 0;

  const expandedAgentId = useMemo(
    () =>
      viewingHidden ? null : activeAgentId ?? sortedAgents[0]?.agent_id ?? null,
    [activeAgentId, sortedAgents, viewingHidden],
  );
  const expandedAgent = useMemo(
    () => sortedAgents.find((a) => a.agent_id === expandedAgentId) ?? null,
    [sortedAgents, expandedAgentId],
  );
  const showSessions = isAgentChatReady(expandedAgent?.state);

  const query = searchQuery.trim().toLowerCase();
  const searching = query.length > 0;
  const matchesSearch = useCallback(
    (name: string) => !searching || name.toLowerCase().includes(query),
    [searching, query],
  );

  // 📌 pinned rows: hidden experts are dropped from the pinned section too (S-6).
  const visiblePinned = useMemo(() => {
    const notHidden = pinnedSessions.filter(
      (s) => !s.agentId || !isHidden(s.agentId),
    );
    return searching
      ? notHidden.filter((s) => s.name.toLowerCase().includes(query))
      : notHidden;
  }, [pinnedSessions, isHidden, searching, query]);

  // Section assignment: only ``inboxByAgent[id].hasActivity`` may decide (PLAN §6).
  const activeSectionAgents = useMemo(
    () =>
      sortedAgents.filter(
        (a) => inboxByAgent[a.agent_id]?.hasActivity === true,
      ),
    [sortedAgents, inboxByAgent],
  );
  const unusedSectionAgents = useMemo(
    () =>
      sortedAgents.filter(
        (a) => inboxByAgent[a.agent_id]?.hasActivity !== true,
      ),
    [sortedAgents, inboxByAgent],
  );

  // The expanded (current) agent stays reachable while searching (S-9).
  const keepAgentRow = useCallback(
    (agent: OctopAgent) =>
      agent.agent_id === expandedAgentId || matchesSearch(agent.name),
    [expandedAgentId, matchesSearch],
  );
  const activeRows = useMemo(
    () => activeSectionAgents.filter(keepAgentRow),
    [activeSectionAgents, keepAgentRow],
  );
  const unusedRows = useMemo(
    () => unusedSectionAgents.filter(keepAgentRow),
    [unusedSectionAgents, keepAgentRow],
  );

  // S-8: with no sessions at all, 📦 is force-expanded so the sidebar is never blank.
  const hasAnySession =
    pinnedSessions.length > 0 || Object.keys(inboxByAgent).length > 0;
  // S-9: the current agent must not be collapsed out of reach.
  const unusedHoldsExpanded = unusedRows.some(
    (a) => a.agent_id === expandedAgentId,
  );
  const unusedVisible =
    unusedExpanded || searching || !hasAnySession || unusedHoldsExpanded;

  const renderAgentRow = useCallback(
    (agent: OctopAgent) => {
      const inboxRow = inboxByAgent[agent.agent_id];
      const sessionCount = inboxRow?.sessionCount ?? 0;
      if (agent.agent_id === expandedAgentId) {
        return (
          <ActiveAgentCard
            key={agent.agent_id}
            agent={agent}
            sessions={sessions}
            sessionCount={sessionCount}
            activeId={activeId}
            searchQuery={searchQuery}
            hasMore={hasMore}
            loadingMore={loadingMore}
            onLoadMore={onLoadMore}
            onFetchAllSessions={onFetchAllSessions}
            onSelect={onSelect}
            onNewChat={onNewChat}
            onDelete={onDelete}
            onRename={onRename}
            onPin={onPin}
            onFork={onFork}
            activeForkDisabled={activeForkDisabled}
            activeForkDisabledHint={activeForkDisabledHint}
            onHide={canHide(agent) ? () => hide(agent.agent_id) : undefined}
          />
        );
      }
      return (
        <InactiveAgentRow
          key={agent.agent_id}
          agent={agent}
          sessionCount={sessionCount}
          onSelect={() => onAgentSelect(agent.agent_id)}
          onNewChat={() => onNewChat(agent.agent_id)}
          onHide={canHide(agent) ? () => hide(agent.agent_id) : undefined}
        />
      );
    },
    [
      inboxByAgent,
      expandedAgentId,
      sessions,
      activeId,
      searchQuery,
      hasMore,
      loadingMore,
      onLoadMore,
      onFetchAllSessions,
      onSelect,
      onNewChat,
      onDelete,
      onRename,
      onPin,
      onFork,
      activeForkDisabled,
      activeForkDisabledHint,
      canHide,
      hide,
      onAgentSelect,
    ],
  );

  return (
    <div className={styles.sessionList}>
      {showSessions ? (
        <div className={styles.sessionSearchWrap}>
          <Search
            size={14}
            className={styles.sessionSearchIcon}
            strokeWidth={2}
          />
          <input
            type="search"
            className={styles.sessionSearchInput}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("chat.searchSessions", "搜索会话")}
            aria-label={t("chat.searchSessions", "搜索会话")}
          />
          <button
            type="button"
            className={styles.sessionAddBtn}
            aria-label={t("common.refresh")}
            title={t("common.refresh")}
            onClick={onRefreshInbox}
          >
            <RefreshCw size={14} aria-hidden />
          </button>
        </div>
      ) : null}

      {agents.length === 0 ? (
        <div className={styles.sessionEmptyAgents}>
          <p className={styles.sessionEmptyAgentsText}>
            {t("chat.noAgentsHint")}
          </p>
          <button
            type="button"
            className={styles.sessionEmptyAgentsLink}
            onClick={() => navigate("/experts")}
          >
            {t("chat.createExpert")}
          </button>
        </div>
      ) : (
        <div className={styles.sessionItems}>
          {viewingHidden ? (
            hiddenAgents.map((agent) => (
              <InactiveAgentRow
                key={agent.agent_id}
                agent={agent}
                onSelect={() => {
                  unhide(agent.agent_id);
                  setShowingHidden(false);
                  onAgentSelect(agent.agent_id);
                }}
                onUnhide={() => unhide(agent.agent_id)}
              />
            ))
          ) : (
            <>
              {/* 📌 置顶段 — cross-agent page-entry snapshot, hidden when empty. */}
              {visiblePinned.length > 0 ? (
                <section data-testid="session-section-pinned">
                  <SessionGroupHeader
                    icon="📌"
                    title={t("chat.sectionPinned")}
                    count={visiblePinned.length}
                  />
                  <div className={styles.agentRowList}>
                    {groupSessionsByProject(visiblePinned).map((group) => (
                      <Fragment key={group.projectId ?? "__no_project__"}>
                        {group.projectId != null && group.projectName ? (
                          <SessionGroupHeader
                            nested
                            title={group.projectName}
                            count={group.sessions.length}
                          />
                        ) : null}
                        {group.sessions.map((session) => {
                          const manage =
                            !session.agentId ||
                            session.agentId === activeAgentId;
                          return (
                            <SessionItem
                              key={session.id}
                              session={session}
                              isActive={activeId === session.id}
                              onSelect={(id) =>
                                onSelect(
                                  id,
                                  session.agentId ?? activeAgentId ?? "",
                                )
                              }
                              onDelete={manage ? onDelete : undefined}
                              onRename={manage ? onRename : undefined}
                              onPin={manage ? onPin : undefined}
                              onFork={manage ? onFork : undefined}
                            />
                          );
                        })}
                      </Fragment>
                    ))}
                  </div>
                </section>
              ) : null}

              {/* 💬 会话段 — agents whose inbox row reports has_activity. */}
              {activeRows.length > 0 ? (
                <section data-testid="session-section-active">
                  <SessionGroupHeader
                    icon="💬"
                    title={t("chat.sectionActive")}
                    count={activeRows.length}
                  />
                  {activeRows.map(renderAgentRow)}
                </section>
              ) : null}

              {/* 📦 未使用段 — default collapsed; force-expanded on search (S-2),
                  when nothing is active (S-8) or when the current agent is here (S-9). */}
              {unusedRows.length > 0 ? (
                <section data-testid="session-section-unused">
                  <SessionGroupHeader
                    icon="📦"
                    title={t("chat.sectionUnused")}
                    count={unusedRows.length}
                    collapsible
                    expanded={unusedVisible}
                    onToggle={() => setUnusedExpanded((v) => !v)}
                  />
                  {unusedVisible ? (
                    <div className={styles.agentRowList}>
                      {unusedRows.map(renderAgentRow)}
                    </div>
                  ) : null}
                </section>
              ) : null}
            </>
          )}
          {hiddenAgents.length > 0 ? (
            <button
              type="button"
              className={styles.expertHiddenToggle}
              onClick={() => setShowingHidden((v) => !v)}
            >
              {viewingHidden
                ? t("chat.expertListShowVisible")
                : t("chat.expertListHidden", { count: hiddenAgents.length })}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
