import { memo, useCallback, useMemo, useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AutoComplete, Checkbox, Dropdown, Modal, Popover, Select } from "antd";
import type { MenuProps } from "antd";
import {
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Folder,
  FolderInput,
  GitFork,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
  Tag,
  Trash2,
  X,
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
import { recordTagClick, readTagClicks } from "../utils/tagFilterClicks";
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
  onDelete: (id: string, compact: boolean) => void | Promise<boolean | void>;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
  folders: string[];
  allTags: string[];
  onSetFolder: (id: string, folder: string | null) => void;
  onSetTags: (id: string, tags: string[]) => void;
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
  folders,
  allTags,
  onSetFolder,
  onSetTags,
}: SessionItemProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(session.name);
  const [folderDialogOpen, setFolderDialogOpen] = useState(false);
  const [folderValue, setFolderValue] = useState("");
  const [tagsDialogOpen, setTagsDialogOpen] = useState(false);
  const [tagsValue, setTagsValue] = useState<string[]>([]);
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

  useEffect(() => {
    if (folderDialogOpen) setFolderValue(session.folder ?? "");
  }, [folderDialogOpen, session.folder]);

  useEffect(() => {
    if (tagsDialogOpen) setTagsValue(session.tags ?? []);
  }, [tagsDialogOpen, session.tags]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== session.name) {
      onRename(session.id, trimmed);
    } else {
      setEditValue(session.name);
    }
    setIsEditing(false);
  }, [editValue, session.name, session.id, onRename]);

  const commitFolder = useCallback(() => {
    onSetFolder(session.id, folderValue.trim() || null);
    setFolderDialogOpen(false);
  }, [folderValue, session.id, onSetFolder]);

  const commitTags = useCallback(() => {
    onSetTags(session.id, tagsValue.map((tag) => tag.trim()).filter(Boolean));
    setTagsDialogOpen(false);
  }, [tagsValue, session.id, onSetTags]);

  const itemForkDisabled = Boolean(forkDisabled) || !session.hasActivity;
  const itemForkHint = !session.hasActivity
    ? t("chat.forkNoAssistant")
    : forkDisabledHint;

  const sessionTags = session.tags ?? [];
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
      key: "folder",
      label: t("chat.folders.moveTo"),
      icon: <FolderInput size={14} />,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        setFolderDialogOpen(true);
      },
    },
    {
      key: "tags",
      label: t("chat.tags.addTag"),
      icon: <Tag size={14} />,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        setTagsDialogOpen(true);
      },
    },
    ...(sessionTags.length > 0
      ? [
          {
            key: "removeTag",
            label: t("chat.tags.removeTag"),
            icon: <X size={14} />,
            children: sessionTags.map((tag) => ({
              key: `remove-${tag}`,
              label: tag,
              onClick: ({ domEvent }: { domEvent: React.SyntheticEvent }) => {
                domEvent.stopPropagation();
                onSetTags(
                  session.id,
                  sessionTags.filter((item) => item !== tag),
                );
              },
            })),
          },
        ]
      : []),
    {
      key: "delete",
      label: t("common.delete", "Delete"),
      icon: <Trash2 size={14} />,
      danger: true,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        confirmDeleteConversation(t, (compact) => {
          void onDelete(session.id, compact);
        });
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
          <Modal
            title={t("chat.folders.moveTo")}
            open={folderDialogOpen}
            onCancel={() => setFolderDialogOpen(false)}
            onOk={commitFolder}
            okText={t("common.confirm")}
            cancelText={t("common.cancel")}
            width={360}
            destroyOnHidden
          >
            <AutoComplete
              value={folderValue}
              onChange={(value) => setFolderValue(value)}
              options={folders.map((folder) => ({
                value: folder,
                label: folder,
              }))}
              placeholder={t("chat.folders.newFolder")}
              style={{ width: "100%" }}
              autoFocus
            />
            {session.folder ? (
              <button
                type="button"
                className={styles.sessionEmptyAgentsLink}
                style={{ marginTop: 10 }}
                onClick={() => {
                  onSetFolder(session.id, null);
                  setFolderDialogOpen(false);
                }}
              >
                {t("chat.folders.ungrouped")}
              </button>
            ) : null}
          </Modal>
          <Modal
            title={t("chat.tags.addTag")}
            open={tagsDialogOpen}
            onCancel={() => setTagsDialogOpen(false)}
            onOk={commitTags}
            okText={t("common.confirm")}
            cancelText={t("common.cancel")}
            width={360}
            destroyOnHidden
          >
            <Select
              mode="tags"
              value={tagsValue}
              onChange={(value) => setTagsValue(value)}
              options={allTags
                .filter((tag) => !sessionTags.includes(tag))
                .map((tag) => ({ value: tag, label: tag }))}
              placeholder={t("chat.tags.addTag")}
              style={{ width: "100%" }}
            />
          </Modal>
        </>
      )}
    </div>
  );
});

const FOLDERS_COLLAPSED_STORAGE_KEY = "octop:chat-folders-collapsed";
const UNGROUPED_FOLDER_KEY = "__ungrouped__";

function readCollapsedFolders(): Set<string> {
  try {
    const raw = localStorage.getItem(FOLDERS_COLLAPSED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function FolderSection({
  folderKey,
  title,
  count,
  children,
}: {
  folderKey: string;
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(() =>
    readCollapsedFolders().has(folderKey),
  );

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        const collapsedSet = readCollapsedFolders();
        if (next) {
          collapsedSet.add(folderKey);
        } else {
          collapsedSet.delete(folderKey);
        }
        localStorage.setItem(
          FOLDERS_COLLAPSED_STORAGE_KEY,
          JSON.stringify(Array.from(collapsedSet)),
        );
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [folderKey]);

  return (
    <div className={styles.folderSection}>
      <button
        type="button"
        className={styles.folderSectionHeader}
        onClick={toggle}
        aria-expanded={!collapsed}
      >
        <span className={styles.folderSectionChevron}>
          {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </span>
        <span className={styles.folderSectionIcon}>
          <Folder size={12} />
        </span>
        <span className={styles.folderSectionName}>{title}</span>
        <span className={styles.folderSectionCount}>{count}</span>
      </button>
      {collapsed ? null : (
        <div className={styles.folderSectionBody}>{children}</div>
      )}
    </div>
  );
}

interface AgentCardProps {
  agent: OctopAgent;
  sessions: Session[];
  activeId: string | null;
  searchQuery: string;
  activeTags: string[];
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onFetchAllSessions: () => void;
  onSelect: (sessionId: string, agentId: string) => void;
  onNewChat: (agentId: string) => void;
  onDelete: (id: string, compact: boolean) => void | Promise<boolean | void>;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string, agentId?: string | null) => void;
  activeForkDisabled?: boolean;
  activeForkDisabledHint?: string;
  folders: string[];
  allTags: string[];
  onSetFolder: (id: string, folder: string | null) => void;
  onSetTags: (id: string, tags: string[]) => void;
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
  activeTags,
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
  folders,
  allTags,
  onSetFolder,
  onSetTags,
  onHide,
  pinned = false,
  onTogglePin,
  liveWorkingIds,
}: AgentCardProps) {
  const { t } = useTranslation();
  const accent = agent.color || "#6366f1";

  const filteredSessions = useMemo(() => {
    let list = sessions;
    if (activeTags.length > 0) {
      list = list.filter((s) =>
        (s.tags ?? []).some((tag) => activeTags.includes(tag)),
      );
    }
    const q = searchQuery.trim().toLowerCase();
    if (!q) return list;
    return list.filter((s) => s.name.toLowerCase().includes(q));
  }, [sessions, searchQuery, activeTags]);

  const folderGroups = useMemo(() => {
    const groups = new Map<string | null, Session[]>();
    for (const session of filteredSessions) {
      const key = session.folder ?? null;
      const bucket = groups.get(key);
      if (bucket) {
        bucket.push(session);
      } else {
        groups.set(key, [session]);
      }
    }
    return groups;
  }, [filteredSessions]);

  const folderKeys = useMemo(() => {
    const keys = Array.from(folderGroups.keys());
    keys.sort((a, b) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return a.localeCompare(b);
    });
    return keys;
  }, [folderGroups]);

  const hasFolders = folderKeys.some((key) => key !== null);

  const renderSessionItem = (session: Session) => (
    <SessionItem
      key={session.id}
      session={session}
      isActive={activeId === session.id}
      workStatus={resolveSessionWorkStatus(session, liveWorkingIds)}
      onSelect={(id) => onSelect(id, agent.agent_id)}
      onDelete={onDelete}
      onRename={onRename}
      onPin={onPin}
      onFork={(id) => onFork(id, agent.agent_id)}
      forkDisabled={activeId === session.id ? activeForkDisabled : undefined}
      forkDisabledHint={
        activeId === session.id ? activeForkDisabledHint : undefined
      }
      folders={folders}
      allTags={allTags}
      onSetFolder={onSetFolder}
      onSetTags={onSetTags}
    />
  );

  const fetchAllRequestedRef = useRef(false);
  useEffect(() => {
    const filtering = Boolean(searchQuery.trim()) || activeTags.length > 0;
    if (!filtering) {
      fetchAllRequestedRef.current = false;
      return;
    }
    if (fetchAllRequestedRef.current) return;
    fetchAllRequestedRef.current = true;
    onFetchAllSessions();
  }, [searchQuery, activeTags, onFetchAllSessions]);

  const showExpandMore =
    hasMore && !searchQuery.trim() && activeTags.length === 0;
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
            {hasFolders
              ? folderKeys.map((folderKey) => {
                  const bucket = folderGroups.get(folderKey) ?? [];
                  if (folderKey === null) {
                    return (
                      <FolderSection
                        key={UNGROUPED_FOLDER_KEY}
                        folderKey={UNGROUPED_FOLDER_KEY}
                        title={t("chat.folders.ungrouped")}
                        count={bucket.length}
                      >
                        {bucket.map(renderSessionItem)}
                      </FolderSection>
                    );
                  }
                  return (
                    <FolderSection
                      key={folderKey}
                      folderKey={folderKey}
                      title={folderKey}
                      count={bucket.length}
                    >
                      {bucket.map(renderSessionItem)}
                    </FolderSection>
                  );
                })
              : filteredSessions.map(renderSessionItem)}
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
  onDelete: (id: string, compact: boolean) => void | Promise<boolean | void>;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string, agentId?: string | null) => void;
  activeForkDisabled?: boolean;
  activeForkDisabledHint?: string;
  folders: string[];
  /** All tags for the agent from the backend; derived tags are merged in as fallback. */
  tags: string[];
  onSetFolder: (id: string, folder: string | null) => void;
  onSetTags: (id: string, tags: string[]) => void;
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
  folders,
  tags,
  onSetFolder,
  onSetTags,
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
      if (!deleted) return false;
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
  const showSessions = isAgentChatReady(
    sortedAgents.find((agent) => agent.agent_id === expandedAgentId)?.state,
  );
  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [tagClickCounts, setTagClickCounts] = useState<Record<string, number>>(
    () => (expandedAgentId ? readTagClicks(expandedAgentId) : {}),
  );

  const allTags = useMemo(() => {
    const tagSet = new Set<string>(tags);
    for (const session of sessions) {
      for (const tag of session.tags ?? []) {
        tagSet.add(tag);
      }
    }
    return Array.from(tagSet).sort((a, b) => a.localeCompare(b));
  }, [tags, sessions]);

  useEffect(() => {
    setActiveTags((prev) => {
      const next = prev.filter((tag) => allTags.includes(tag));
      return next.length === prev.length ? prev : next;
    });
  }, [allTags]);

  useEffect(() => {
    setTagClickCounts(expandedAgentId ? readTagClicks(expandedAgentId) : {});
  }, [expandedAgentId]);

  const toggleTag = useCallback(
    (tag: string, nextChecked?: boolean) => {
      const currentlyChecked = activeTags.includes(tag);
      const checked = nextChecked ?? !currentlyChecked;
      if (checked === currentlyChecked) return;

      setActiveTags((prev) =>
        checked ? [...prev, tag] : prev.filter((item) => item !== tag),
      );
      if (checked && expandedAgentId) {
        recordTagClick(expandedAgentId, tag);
        setTagClickCounts(readTagClicks(expandedAgentId));
      }
    },
    [activeTags, expandedAgentId],
  );

  const quickTags = useMemo(
    () =>
      [...allTags]
        .sort((a, b) => {
          const countDiff = (tagClickCounts[b] ?? 0) - (tagClickCounts[a] ?? 0);
          return countDiff || a.localeCompare(b);
        })
        .slice(0, 3),
    [allTags, tagClickCounts],
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

      {showSessions && allTags.length > 0 ? (
        <div className={styles.tagFilterRow}>
          <Popover
            trigger="click"
            placement="bottomLeft"
            arrow={false}
            content={
              <div className={styles.tagFilterPopover}>
                <div className={styles.tagFilterPopoverList}>
                  {allTags.map((tag) => (
                    <label key={tag} className={styles.tagFilterOption}>
                      <Checkbox
                        checked={activeTags.includes(tag)}
                        onChange={(e) => toggleTag(tag, e.target.checked)}
                      >
                        {tag}
                      </Checkbox>
                    </label>
                  ))}
                </div>
                <button
                  type="button"
                  className={styles.tagFilterClear}
                  disabled={activeTags.length === 0}
                  onClick={() => setActiveTags([])}
                >
                  {t("chat.tags.clearFilter")}
                </button>
              </div>
            }
          >
            <button
              type="button"
              className={`${styles.tagFilterBtn} ${
                activeTags.length > 0 ? styles.tagFilterBtnActive : ""
              }`}
            >
              <Tag size={12} />
              <span>{t("chat.tags.filterByTag")}</span>
              {activeTags.length > 0 ? (
                <span className={styles.tagFilterBadge}>
                  {activeTags.length}
                </span>
              ) : null}
            </button>
          </Popover>
          {quickTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className={`${styles.tagFilterChip} ${
                activeTags.includes(tag) ? styles.tagFilterChipActive : ""
              }`}
              onClick={() => toggleTag(tag)}
            >
              {tag}
            </button>
          ))}
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
                    activeTags={activeTags}
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
                    folders={folders}
                    allTags={allTags}
                    onSetFolder={onSetFolder}
                    onSetTags={onSetTags}
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
