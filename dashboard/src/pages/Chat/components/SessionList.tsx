import { memo, useCallback, useMemo, useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import {
  Eye,
  EyeOff,
  GitFork,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
  Trash2,
} from "lucide-react";
import type { Session } from "../hooks/useSessions";
import type { OctopAgent } from "../../../context/AgentContext";
import { isAgentChatReady } from "../../../utils/agentError";
import {
  confirmDeleteConversation,
  deleteConversation,
} from "../utils/deleteConversation";
import { isImeComposing } from "../../../utils/ime";
import { ExpertIcon } from "../../Experts/components/iconForName";
import { useHiddenSharedExperts } from "../hooks/useHiddenSharedExperts";
import SessionChannelIcon from "./SessionChannelIcon";
import SessionWorkStatusIcon from "./SessionWorkStatusIcon";
import SharedExpertHint from "./SharedExpertHint";
import RemoteExpertHint from "./RemoteExpertHint";
import TeamChatBadge from "./TeamChatBadge";
import { useExpertSessionCatalog } from "../hooks/useExpertSessionCatalog";
import { usePinnedExperts } from "../hooks/usePinnedExperts";
import { useSessionWorkIds } from "../hooks/useSessionWorkIds";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { formatThreadTitle } from "../utils/threadTitle";
import {
  expertVisibleInNavSearch,
  matchesNavQuery,
} from "../utils/navSessionSearch";
import { sortExpertsByPin } from "../utils/pinnedExpertsPrefs";
import {
  initialChatNavScope,
  matchesChatNavScope,
  type ChatNavScope,
} from "../utils/chatNavScope";
import ChatNavScopeTabs, { ChatNavScopeEmpty } from "./ChatNavScopeTabs";
import ExpertNameLabel from "./ExpertNameLabel";
import ExpertNavActions from "./ExpertNavActions";
import {
  resolveSessionWorkStatus,
  type SessionWorkStatus,
} from "../utils/sessionWorkStatus";
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

interface SessionItemProps {
  session: Session;
  isActive: boolean;
  workStatus?: SessionWorkStatus;
  onSelect: (id: string) => void;
  onDelete: (
    id: string,
    compact: boolean,
  ) => void | Promise<boolean | null | void>;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
}

const SessionItem = memo(function SessionItem({
  session,
  isActive,
  workStatus = "idle",
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
      onRename(session.id, trimmed);
    } else {
      setEditValue(session.name);
    }
    setIsEditing(false);
  }, [editValue, session.name, session.id, onRename]);

  const itemForkDisabled = Boolean(forkDisabled) || !session.hasActivity;
  const itemForkHint = !session.hasActivity
    ? t("chat.forkNoAssistant")
    : forkDisabledHint;

  const menuItems: MenuProps["items"] = [
    {
      key: "pin",
      label: session.pinned
        ? t("chat.unpin", "取消置顶")
        : t("chat.pin", "置顶"),
      icon: session.pinned ? <PinOff size={14} /> : <Pin size={14} />,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        onPin(session.id, !session.pinned);
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
        onFork(session.id);
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
        confirmDeleteConversation(t, (compact) =>
          onDelete(session.id, compact),
        );
      },
    },
  ];

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
      <span className={styles.sessionRowLead}>
        {workStatus !== "idle" ? (
          <SessionWorkStatusIcon status={workStatus} />
        ) : (
          <SessionChannelIcon
            channelType={session.channelType}
            size={12}
            className={styles.sessionRowIcon}
          />
        )}
      </span>
      {isEditing ? (
        <input
          ref={inputRef}
          className={styles.sessionNameInput}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (isImeComposing(e)) return;
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
          {session.pinned ? (
            <span
              className={styles.sessionRowPinIndicator}
              title={t("chat.unpin")}
            >
              <Pin size={12} strokeWidth={2} />
            </span>
          ) : null}
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
        </>
      )}
    </div>
  );
});

interface AgentCardProps {
  agent: OctopAgent;
  sessions: Session[];
  activeId: string | null;
  searchQuery: string;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onFetchAllSessions: () => void;
  onSelect: (sessionId: string, agentId: string) => void;
  onNewChat: (agentId: string) => void;
  onDelete: (
    id: string,
    compact: boolean,
  ) => void | Promise<boolean | null | void>;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string, agentId?: string | null) => void;
  activeForkDisabled?: boolean;
  activeForkDisabledHint?: string;
  onHide?: () => void;
  pinned?: boolean;
  onTogglePin?: () => void;
  liveWorkingIds: ReadonlySet<string>;
}

function ActiveAgentCard({
  agent,
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
  onHide,
  pinned = false,
  onTogglePin,
  liveWorkingIds,
}: AgentCardProps) {
  const { t } = useTranslation();
  const accent = agent.color || "#6366f1";

  const filteredSessions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => s.name.toLowerCase().includes(q));
  }, [sessions, searchQuery]);

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
            size={agent.icon_url?.trim() ? 28 : 16}
          />
        </div>
        <div className={styles.agentCardInfo}>
          <div className={styles.agentCardNameRow}>
            <div className={styles.agentNameCluster}>
              <ExpertNameLabel
                name={agent.name}
                className={styles.agentCardName}
              />
              <TeamChatBadge agent={agent} />
              <SharedExpertHint agent={agent} />
              <RemoteExpertHint agent={agent} />
            </div>
            <AgentUnreadBadge count={agent.unread_count ?? 0} />
            {onTogglePin ? (
              <ExpertNavActions
                variant="classic"
                pinned={pinned}
                onTogglePin={onTogglePin}
                onNewChat={() => onNewChat(agent.agent_id)}
              />
            ) : null}
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
            {filteredSessions.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                isActive={activeId === s.id}
                workStatus={resolveSessionWorkStatus(s, liveWorkingIds)}
                onSelect={(id) => onSelect(id, agent.agent_id)}
                onDelete={onDelete}
                onRename={onRename}
                onPin={onPin}
                onFork={(id) => onFork(id, agent.agent_id)}
                forkDisabled={
                  activeId === s.id ? activeForkDisabled : undefined
                }
                forkDisabledHint={
                  activeId === s.id ? activeForkDisabledHint : undefined
                }
              />
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
  onSelect: () => void;
  onNewChat?: () => void;
  onHide?: () => void;
  onUnhide?: () => void;
  pinned?: boolean;
  onTogglePin?: () => void;
}

function InactiveAgentRow({
  agent,
  onSelect,
  onNewChat,
  onHide,
  onUnhide,
  pinned = false,
  onTogglePin,
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
            size={agent.icon_url?.trim() ? 26 : 14}
          />
        </div>
        <div className={styles.agentRowInfo}>
          <div className={styles.agentRowNameRow}>
            <div className={styles.agentNameCluster}>
              <ExpertNameLabel
                name={agent.name}
                className={styles.agentRowName}
              />
              <TeamChatBadge agent={agent} />
              <SharedExpertHint agent={agent} />
              <RemoteExpertHint agent={agent} />
            </div>
            <AgentUnreadBadge count={agent.unread_count ?? 0} />
            {onNewChat && onTogglePin ? (
              <ExpertNavActions
                variant="classic"
                pinned={pinned}
                onTogglePin={onTogglePin}
                onNewChat={onNewChat}
              />
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
  onLoadMore: () => void;
  onFetchAllSessions: () => void;
  onSelect: (sessionId: string, agentId: string) => void;
  onAgentSelect: (agentId: string) => void;
  onNewChat: (agentId: string) => void;
  onDelete: (
    id: string,
    compact: boolean,
  ) => void | Promise<boolean | null | void>;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string, agentId?: string | null) => void;
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
  onLoadMore,
  onFetchAllSessions,
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
  const liveWorkingIds = useSessionWorkIds();
  const [searchQuery, setSearchQuery] = useState("");
  const [showingHidden, setShowingHidden] = useState(false);
  const [navScope, setNavScope] = useState<ChatNavScope>(() =>
    initialChatNavScope(
      agents.find((agent) => agent.agent_id === activeAgentId),
    ),
  );
  const { filterVisible, pickHidden, hide, unhide, canHide } =
    useHiddenSharedExperts();
  const { pinnedIds, isPinned, togglePin } = usePinnedExperts();

  const hiddenAgents = useMemo(
    () =>
      sortExpertsByPin(pickHidden(agents), pinnedIds).filter((agent) =>
        matchesChatNavScope(agent, navScope),
      ),
    [agents, pickHidden, pinnedIds, navScope],
  );

  const sortedAgents = useMemo(() => {
    const visible = filterVisible(agents, {
      keepAgentIds: activeAgentId ? [activeAgentId] : [],
    });
    return sortExpertsByPin(visible, pinnedIds).filter((agent) =>
      matchesChatNavScope(agent, navScope),
    );
  }, [agents, filterVisible, activeAgentId, pinnedIds, navScope]);

  // Leave the hidden-only view once nothing remains hidden.
  const viewingHidden = showingHidden && hiddenAgents.length > 0;
  const agentsToRender = viewingHidden ? hiddenAgents : sortedAgents;

  const expandedAgentId = useMemo(() => {
    if (viewingHidden) return null;
    const activeInScope = sortedAgents.some(
      (agent) => agent.agent_id === activeAgentId,
    );
    if (activeInScope) return activeAgentId;
    // Browsing another tab keeps the open chat; don't expand a stranger.
    if (activeAgentId) return null;
    return sortedAgents[0]?.agent_id ?? null;
  }, [activeAgentId, sortedAgents, viewingHidden]);
  const searching = searchQuery.trim().length > 0;
  const fetchAllRequestedRef = useRef(false);
  useEffect(() => {
    if (!searching) {
      fetchAllRequestedRef.current = false;
      return;
    }
    if (fetchAllRequestedRef.current) return;
    fetchAllRequestedRef.current = true;
    onFetchAllSessions();
  }, [onFetchAllSessions, searching]);
  const catalog = useExpertSessionCatalog(
    viewingHidden ? hiddenAgents : sortedAgents,
    searching && !viewingHidden,
  );
  const sessionsFor = useCallback(
    (agentId: string): Session[] => {
      const catalogList = catalog.byAgent[agentId] ?? [];
      if (agentId === activeAgentId && sessions.length >= catalogList.length) {
        return sessions;
      }
      return catalogList.length > 0
        ? catalogList
        : agentId === activeAgentId
        ? sessions
        : [];
    },
    [activeAgentId, catalog.byAgent, sessions],
  );
  const listedAgents = useMemo(() => {
    if (viewingHidden) {
      if (!searching) return agentsToRender;
      return agentsToRender.filter((agent) =>
        matchesNavQuery(agent.name, searchQuery),
      );
    }
    if (!searching) return agentsToRender;
    return agentsToRender.filter((agent) =>
      expertVisibleInNavSearch(
        agent.name,
        sessionsFor(agent.agent_id).map((session) => session.name),
        searchQuery,
      ),
    );
  }, [agentsToRender, searchQuery, searching, sessionsFor, viewingHidden]);

  const deleteOther = useCallback(
    async (agentId: string, id: string, compact: boolean) => {
      const deleted = await deleteConversation(agentId, id, compact, t);
      if (deleted !== true) return deleted;
      catalog.patch(agentId, (prev) =>
        prev.filter((session) => session.id !== id),
      );
      return true;
    },
    [catalog, t],
  );
  const renameOther = useCallback(
    (agentId: string, id: string, name: string) => {
      const next = formatThreadTitle(name) || name.trim();
      if (!next) return;
      void octopThreadsApi.rename(agentId, id, next).catch(() => {});
      catalog.patch(agentId, (prev) =>
        prev.map((session) =>
          session.id === id ? { ...session, name: next } : session,
        ),
      );
    },
    [catalog],
  );
  const pinOther = useCallback(
    (agentId: string, id: string, pinned: boolean) => {
      void octopThreadsApi.patch(agentId, id, { pinned }).catch(() => {});
      catalog.patch(agentId, (prev) =>
        prev.map((session) =>
          session.id === id ? { ...session, pinned } : session,
        ),
      );
    },
    [catalog],
  );

  return (
    <div className={styles.sessionList}>
      {agents.length > 0 ? (
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
        </div>
      ) : null}

      {agents.length > 0 ? (
        <ChatNavScopeTabs value={navScope} onChange={setNavScope} />
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
          ) : listedAgents.length === 0 ? (
            searching || catalog.loading ? (
              <div className={styles.agentCardSessionsEmpty}>
                {catalog.loading
                  ? t("common.loading")
                  : t("chat.noSearchResults", "没有匹配的会话")}
              </div>
            ) : (
              <ChatNavScopeEmpty scope={navScope} />
            )
          ) : (
            listedAgents.map((agent) => {
              const isActive = agent.agent_id === activeAgentId;
              const hits = searching
                ? sessionsFor(agent.agent_id).filter((session) =>
                    matchesNavQuery(session.name, searchQuery),
                  )
                : [];
              const expanded = searching
                ? hits.length > 0
                : agent.agent_id === expandedAgentId;
              if (expanded) {
                return (
                  <ActiveAgentCard
                    key={agent.agent_id}
                    agent={agent}
                    sessions={isActive ? sessions : hits}
                    activeId={activeId}
                    searchQuery={isActive ? searchQuery : ""}
                    hasMore={isActive ? hasMore : false}
                    loadingMore={isActive ? loadingMore : false}
                    onLoadMore={isActive ? onLoadMore : () => undefined}
                    onFetchAllSessions={
                      isActive ? onFetchAllSessions : () => undefined
                    }
                    onSelect={onSelect}
                    onNewChat={onNewChat}
                    onDelete={
                      isActive
                        ? onDelete
                        : (id, compact) =>
                            deleteOther(agent.agent_id, id, compact)
                    }
                    onRename={
                      isActive
                        ? onRename
                        : (id, name) => renameOther(agent.agent_id, id, name)
                    }
                    onPin={
                      isActive
                        ? onPin
                        : (id, pinned) => pinOther(agent.agent_id, id, pinned)
                    }
                    onFork={onFork}
                    activeForkDisabled={activeForkDisabled}
                    activeForkDisabledHint={activeForkDisabledHint}
                    onHide={
                      canHide(agent) ? () => hide(agent.agent_id) : undefined
                    }
                    pinned={isPinned(agent.agent_id)}
                    onTogglePin={() => togglePin(agent.agent_id)}
                    liveWorkingIds={liveWorkingIds}
                  />
                );
              }
              return (
                <InactiveAgentRow
                  key={agent.agent_id}
                  agent={agent}
                  onSelect={() => onAgentSelect(agent.agent_id)}
                  onNewChat={() => onNewChat(agent.agent_id)}
                  onHide={
                    canHide(agent) ? () => hide(agent.agent_id) : undefined
                  }
                  pinned={isPinned(agent.agent_id)}
                  onTogglePin={() => togglePin(agent.agent_id)}
                />
              );
            })
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
