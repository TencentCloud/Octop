import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  GitFork,
  ChevronRight,
} from "lucide-react";
import type { OctopAgent } from "../../../context/AgentContext";
import { ExpertIcon } from "../../Experts/components/iconForName";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { showConfirmModal } from "../../../utils/confirmModal";
import { isAgentChatReady } from "../../../utils/agentError";
import {
  sortSessions,
  toSession,
  type Session,
  scheduleSessionTitleRefresh,
  TITLE_REFRESH_DELAYS_MS,
} from "../hooks/useSessions";
import { formatThreadTitle } from "../utils/threadTitle";
import { onSessionEvent, onStreamEvent } from "../hooks/chatStore";
import { SessionRowTitle } from "./SessionRowTitle";
import styles from "../index.module.less";

/** Default preview size per expert in minimal nav (matches session page size). */
export const MINIMAL_AGENT_SESSION_PREVIEW = 10;

const FOLDER_COLLAPSED_KEY = "octop:minimal-agent-folders-collapsed";

function loadCollapsedFolders(): Set<string> {
  try {
    const raw = localStorage.getItem(FOLDER_COLLAPSED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((x): x is string => typeof x === "string"));
    }
  } catch {
    /* ignore */
  }
  return new Set();
}

function saveCollapsedFolders(collapsed: Set<string>) {
  try {
    localStorage.setItem(FOLDER_COLLAPSED_KEY, JSON.stringify([...collapsed]));
  } catch {
    /* ignore */
  }
}

interface MinimalAgentSessionNavProps {
  agents: OctopAgent[];
  activeId: string | null;
  activeAgentId: string | null;
  /** Live sessions for the currently active agent (keeps nav in sync). */
  activeSessions: Session[];
  onSelect: (sessionId: string, agentId: string) => void;
  onAgentSelect: (agentId: string) => void;
  onDeleteActive: (id: string) => void;
  onRenameActive: (id: string, name: string) => void;
  onPinActive: (id: string, pinned: boolean) => void;
  onFork: (id: string, agentId?: string | null) => void;
  activeForkDisabled?: boolean;
  activeForkDisabledHint?: string;
}

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

const PreviewSessionRow = memo(function PreviewSessionRow({
  session,
  isActive,
  onSelect,
  onDelete,
  onRename,
  onPin,
  onFork,
  forkDisabled,
  forkDisabledHint,
}: {
  session: Session;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
}) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [rowHovered, setRowHovered] = useState(false);
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
        showConfirmModal({
          title: t("chat.deleteSessionConfirm"),
          okText: t("common.delete"),
          cancelText: t("common.cancel"),
          okButtonProps: { danger: true },
          onOk: () => {
            onDelete(session.id);
          },
        });
      },
    },
  ];

  return (
    <div
      className={`${styles.sessionRow} ${styles.sessionRowCompact} ${
        isActive ? styles.sessionRowActive : ""
      } ${session.pinned ? styles.sessionRowPinned : ""}`}
      onMouseEnter={() => !isEditing && setRowHovered(true)}
      onMouseLeave={() => setRowHovered(false)}
      onClick={() => {
        if (!isEditing) onSelect(session.id);
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !isEditing) onSelect(session.id);
      }}
    >
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
          <SessionRowTitle
            text={session.name}
            className={styles.sessionRowTitle}
            hovered={rowHovered}
          />
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

export default function MinimalAgentSessionNav({
  agents,
  activeId,
  activeAgentId,
  activeSessions,
  onSelect,
  onAgentSelect,
  onDeleteActive,
  onRenameActive,
  onPinActive,
  onFork,
  activeForkDisabled,
  activeForkDisabledHint,
}: MinimalAgentSessionNavProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [byAgent, setByAgent] = useState<Record<string, Session[]>>({});
  const [loading, setLoading] = useState(false);
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(() =>
    loadCollapsedFolders(),
  );
  const agentKey = useMemo(
    () =>
      [...agents]
        .map((a) => a.agent_id)
        .sort()
        .join(","),
    [agents],
  );

  const sortedAgents = useMemo(
    () => [...agents].sort((a, b) => b.id - a.id),
    [agents],
  );

  // Ensure the active expert folder stays open.
  useEffect(() => {
    if (!activeAgentId) return;
    setCollapsedFolders((prev) => {
      if (!prev.has(activeAgentId)) return prev;
      const next = new Set(prev);
      next.delete(activeAgentId);
      saveCollapsedFolders(next);
      return next;
    });
  }, [activeAgentId]);

  const toggleFolder = useCallback((agentId: string) => {
    setCollapsedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      saveCollapsedFolders(next);
      return next;
    });
  }, []);

  const openFolderAndSelect = useCallback(
    (agentId: string) => {
      setCollapsedFolders((prev) => {
        if (!prev.has(agentId)) return prev;
        const next = new Set(prev);
        next.delete(agentId);
        saveCollapsedFolders(next);
        return next;
      });
      onAgentSelect(agentId);
    },
    [onAgentSelect],
  );

  // Fetch preview threads for every expert (independent of classic session store).
  useEffect(() => {
    if (!agentKey) {
      setByAgent({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      const entries = await Promise.all(
        agentKey.split(",").map(async (id) => {
          if (!id) return [id, [] as Session[]] as const;
          try {
            const rows = await octopThreadsApi.list(
              id,
              MINIMAL_AGENT_SESSION_PREVIEW,
            );
            return [
              id,
              sortSessions(rows.map(toSession)).slice(
                0,
                MINIMAL_AGENT_SESSION_PREVIEW,
              ),
            ] as const;
          } catch {
            return [id, [] as Session[]] as const;
          }
        }),
      );
      if (!cancelled) {
        setByAgent(Object.fromEntries(entries));
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentKey]);

  // Keep the active agent's preview aligned with live chat session store.
  // Skip empty lists — standalone host passes [] and must not wipe fetched previews
  // when the user selects a session (activeAgentId updates).
  useEffect(() => {
    if (!activeAgentId || activeSessions.length === 0) return;
    setByAgent((prev) => ({
      ...prev,
      [activeAgentId]: sortSessions(activeSessions).slice(
        0,
        MINIMAL_AGENT_SESSION_PREVIEW,
      ),
    }));
  }, [activeAgentId, activeSessions]);

  const refreshAgentPreview = useCallback(async (agentId: string) => {
    if (!agentId) return;
    try {
      const rows = await octopThreadsApi.list(
        agentId,
        MINIMAL_AGENT_SESSION_PREVIEW,
      );
      setByAgent((prev) => ({
        ...prev,
        [agentId]: sortSessions(rows.map(toSession)).slice(
          0,
          MINIMAL_AGENT_SESSION_PREVIEW,
        ),
      }));
    } catch {
      /* ignore */
    }
  }, []);

  // Distilled titles arrive async (often 30–60s); refetch preview list after each turn.
  useEffect(() => {
    if (!activeAgentId) return;
    return onStreamEvent((event) => {
      if (event.kind !== "streamEnd") return;
      scheduleSessionTitleRefresh(activeAgentId, event.sessionId);
      for (const delay of TITLE_REFRESH_DELAYS_MS) {
        window.setTimeout(() => {
          void refreshAgentPreview(activeAgentId);
        }, delay);
      }
    });
  }, [activeAgentId, refreshAgentPreview]);

  useEffect(() => {
    return onSessionEvent((event) => {
      if (event.kind !== "sessionDeleted") return;
      const { sessionId } = event;
      setByAgent((prev) => {
        const next: Record<string, Session[]> = {};
        for (const [aid, list] of Object.entries(prev)) {
          next[aid] = list.filter((s) => s.id !== sessionId);
        }
        return next;
      });
    });
  }, []);

  const patchLocal = useCallback(
    (agentId: string, updater: (prev: Session[]) => Session[]) => {
      setByAgent((prev) => ({
        ...prev,
        [agentId]: sortSessions(updater(prev[agentId] ?? [])).slice(
          0,
          MINIMAL_AGENT_SESSION_PREVIEW,
        ),
      }));
    },
    [],
  );

  const handleDelete = useCallback(
    async (agentId: string, sessionId: string) => {
      if (agentId === activeAgentId) {
        onDeleteActive(sessionId);
        patchLocal(agentId, (prev) => prev.filter((s) => s.id !== sessionId));
        return;
      }
      try {
        await octopThreadsApi.delete(agentId, sessionId);
        patchLocal(agentId, (prev) => prev.filter((s) => s.id !== sessionId));
      } catch {
        /* ignore */
      }
    },
    [activeAgentId, onDeleteActive, patchLocal],
  );

  const handleRename = useCallback(
    (agentId: string, sessionId: string, name: string) => {
      const next = formatThreadTitle(name) || name.trim();
      if (!next) return;
      if (agentId === activeAgentId) {
        onRenameActive(sessionId, next);
      } else {
        void octopThreadsApi.rename(agentId, sessionId, next).catch(() => {});
      }
      patchLocal(agentId, (prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, name: next } : s)),
      );
    },
    [activeAgentId, onRenameActive, patchLocal],
  );

  const handlePin = useCallback(
    (agentId: string, sessionId: string, pinned: boolean) => {
      if (agentId === activeAgentId) {
        onPinActive(sessionId, pinned);
      } else {
        void octopThreadsApi
          .patch(agentId, sessionId, { pinned })
          .catch(() => {});
      }
      patchLocal(agentId, (prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, pinned } : s)),
      );
    },
    [activeAgentId, onPinActive, patchLocal],
  );

  if (agents.length === 0) {
    return (
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
    );
  }

  return (
    <div className={`${styles.sessionList} ${styles.minimalAgentNav}`}>
      {sortedAgents.map((agent) => {
        const list = byAgent[agent.agent_id] ?? [];
        const ready = isAgentChatReady(agent.state);
        const expanded = !collapsedFolders.has(agent.agent_id);

        return (
          <section key={agent.agent_id} className={styles.minimalAgentSection}>
            <div className={styles.minimalAgentHeader}>
              <button
                type="button"
                className={styles.minimalAgentFolderBtn}
                onClick={() => openFolderAndSelect(agent.agent_id)}
              >
                <span
                  className={styles.minimalAgentAvatar}
                  style={{
                    color: agent.color || "var(--fn-text-tertiary)",
                    background: `${agent.color || "#6366f1"}14`,
                  }}
                >
                  <ExpertIcon
                    iconUrl={agent.icon_url}
                    iconName={agent.icon_name}
                    size={14}
                  />
                </span>
                <span className={styles.minimalAgentName}>{agent.name}</span>
                <AgentUnreadBadge count={agent.unread_count ?? 0} />
              </button>
              <button
                type="button"
                className={styles.minimalAgentChevronBtn}
                aria-expanded={expanded}
                aria-label={
                  expanded ? t("nav.collapseSidebar") : t("nav.expandSidebar")
                }
                onClick={() => toggleFolder(agent.agent_id)}
              >
                <ChevronRight
                  size={14}
                  strokeWidth={2}
                  className={`${styles.minimalAgentChevron} ${
                    expanded ? styles.minimalAgentChevronOpen : ""
                  }`}
                  aria-hidden
                />
              </button>
            </div>

            {expanded ? (
              <div className={styles.minimalAgentSessions}>
                {!ready ? (
                  <div className={styles.minimalAgentEmpty}>
                    {t("chat.agentNotRunningHint")}
                  </div>
                ) : loading && list.length === 0 ? (
                  <div className={styles.minimalAgentEmpty}>
                    {t("common.loading")}
                  </div>
                ) : list.length === 0 ? (
                  <div className={styles.minimalAgentEmpty}>
                    {t("chat.noSessionsYet", "直接发消息即可开始对话")}
                  </div>
                ) : (
                  list.map((session) => (
                    <PreviewSessionRow
                      key={session.id}
                      session={session}
                      isActive={session.id === activeId}
                      onSelect={(id) => onSelect(id, agent.agent_id)}
                      onDelete={(id) => void handleDelete(agent.agent_id, id)}
                      onRename={(id, name) =>
                        handleRename(agent.agent_id, id, name)
                      }
                      onPin={(id, pinned) =>
                        handlePin(agent.agent_id, id, pinned)
                      }
                      onFork={(id) => onFork(id, agent.agent_id)}
                      forkDisabled={
                        session.id === activeId ? activeForkDisabled : undefined
                      }
                      forkDisabledHint={
                        session.id === activeId
                          ? activeForkDisabledHint
                          : undefined
                      }
                    />
                  ))
                )}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
