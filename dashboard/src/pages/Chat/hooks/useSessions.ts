import { useCallback, useEffect, useSyncExternalStore } from "react";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { onSessionEvent } from "./chatStore";

export interface Session {
  id: string;
  name: string;
  threadId: string;
  updatedAt: string | null;
  channelType: string;
  isActive?: boolean;
  hasActivity?: boolean;
  pinned?: boolean;
}

/** Result of probing whether a thread exists for the current agent. */
export type ThreadProbeResult = "found" | "missing" | "unknown";

export function toSession(row: {
  thread_id: string;
  title: string | null;
  last_active: number;
  channel_type?: string;
  is_active?: boolean;
  has_messages?: boolean;
  pinned?: boolean;
}): Session {
  const hasActivity =
    Boolean(row.has_messages) || Boolean(row.title) || row.last_active > 0;
  return {
    id: row.thread_id,
    name: row.title || "New Chat",
    threadId: row.thread_id,
    updatedAt: row.last_active
      ? new Date(row.last_active * 1000).toISOString()
      : null,
    channelType: row.channel_type ?? "dashboard",
    isActive: row.is_active ?? false,
    hasActivity,
    pinned: Boolean(row.pinned),
  };
}

function sortSessions(sessions: Session[]): Session[] {
  return [...sessions].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return 0;
  });
}

/** Pick the thread bound to the dashboard session_key, else best history candidate. */
export function pickPreferredSession(sessions: Session[]): Session | null {
  if (sessions.length === 0) return null;
  return (
    sessions.find((s) => s.isActive) ??
    sessions.find((s) => s.hasActivity && s.name !== "New Chat") ??
    sessions.find((s) => s.hasActivity) ??
    sessions.find((s) => s.name !== "New Chat") ??
    sessions[0]
  );
}

let _sessions: Session[] = [];
let _loading = true;
let _hasMore = false;
let _loadingMore = false;
export const SESSION_PAGE_SIZE = 5;
let _storeAgentId: string | null = null;
const _loadedLimitByAgent = new Map<string, number>();
const _listeners = new Set<() => void>();

/** Thread ids mid-create; stale-thread redirect must ignore these until listed. */
const _pendingThreadIds = new Set<string>();

export function markPendingThread(threadId: string) {
  _pendingThreadIds.add(threadId);
}

export function clearPendingThread(threadId: string) {
  _pendingThreadIds.delete(threadId);
}

export function isPendingThread(threadId: string): boolean {
  return threadId === "__pending__" || _pendingThreadIds.has(threadId);
}

function notifyListeners() {
  for (const cb of _listeners) cb();
}

function setModuleSessions(
  updater: Session[] | ((prev: Session[]) => Session[]),
) {
  _sessions = typeof updater === "function" ? updater(_sessions) : updater;
  _snapshot = {
    sessions: _sessions,
    loading: _loading,
    hasMore: _hasMore,
    loadingMore: _loadingMore,
  };
  notifyListeners();
}

function setModuleLoading(value: boolean) {
  _loading = value;
  _snapshot = {
    sessions: _sessions,
    loading: _loading,
    hasMore: _hasMore,
    loadingMore: _loadingMore,
  };
  notifyListeners();
}

function subscribeSessionStore(cb: () => void) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

let _snapshot = {
  sessions: _sessions,
  loading: _loading,
  hasMore: _hasMore,
  loadingMore: _loadingMore,
};

function getSessionSnapshot() {
  return _snapshot;
}

export function isTempSessionId(id: string): boolean {
  void id;
  return false;
}

function getLoadedLimit(agentId: string): number {
  return _loadedLimitByAgent.get(agentId) ?? SESSION_PAGE_SIZE;
}

function resetSessionPagination(agentId: string) {
  _loadedLimitByAgent.set(agentId, SESSION_PAGE_SIZE);
  _hasMore = false;
  _loadingMore = false;
}

function visibleSessionsForAgent(
  sessions: Session[],
  agentId: string,
  activeThreadId?: string,
): Session[] {
  const limit = getLoadedLimit(agentId);
  let visible = sessions.slice(0, limit);
  if (!activeThreadId || visible.some((s) => s.id === activeThreadId)) {
    return visible;
  }
  const active = sessions.find((s) => s.id === activeThreadId);
  if (!active) return visible;
  visible = [active, ...visible.filter((s) => s.id !== activeThreadId)];
  return visible.slice(0, limit);
}

async function fetchSessionsPage(
  agentId: string,
  limit: number,
): Promise<{ sessions: Session[]; hasMore: boolean }> {
  const rows = await octopThreadsApi.list(agentId, limit + 1);
  const hasMore = rows.length > limit;
  const sessions = sortSessions(rows.slice(0, limit).map(toSession));
  return { sessions, hasMore };
}

function applySessionPage(
  allSessions: Session[],
  hasMore: boolean,
  limit: number,
  agentId: string,
  activeThreadId?: string,
) {
  _loadedLimitByAgent.set(agentId, limit);
  _hasMore = hasMore;
  setModuleSessions(
    visibleSessionsForAgent(allSessions, agentId, activeThreadId),
  );
}

function setModuleLoadingMore(value: boolean) {
  _loadingMore = value;
  _snapshot = {
    sessions: _sessions,
    loading: _loading,
    hasMore: _hasMore,
    loadingMore: _loadingMore,
  };
  notifyListeners();
}

/**
 * Drop previous-agent threads before the first paint of a new agent.
 * Clearing only in useEffect leaks stale sessions for one render, and
 * chat nav can then write `/chat/{newAgent}/{oldThread}` into the URL.
 */
function syncStoreToAgent(agentId: string | null) {
  if (_storeAgentId === agentId) return;
  _storeAgentId = agentId;
  _sessions = [];
  _loading = agentId != null;
  _hasMore = false;
  _loadingMore = false;
  _snapshot = {
    sessions: _sessions,
    loading: _loading,
    hasMore: _hasMore,
    loadingMore: _loadingMore,
  };
}

/** Reset module session store between vitest cases. */
export function resetSessionStoreForTests() {
  _storeAgentId = null;
  _sessions = [];
  _loading = true;
  _hasMore = false;
  _loadingMore = false;
  _loadedLimitByAgent.clear();
  _pendingThreadIds.clear();
  _snapshot = {
    sessions: _sessions,
    loading: _loading,
    hasMore: _hasMore,
    loadingMore: _loadingMore,
  };
}

export function useSessions(agentId: string | null) {
  syncStoreToAgent(agentId);
  const { sessions, loading, hasMore, loadingMore } = useSyncExternalStore(
    subscribeSessionStore,
    getSessionSnapshot,
  );

  const fetchSessions = useCallback(
    async (activeThreadId?: string) => {
      if (!agentId) {
        setModuleSessions([]);
        setModuleLoading(false);
        return [];
      }
      try {
        const limit = getLoadedLimit(agentId);
        const { sessions: valid, hasMore: more } = await fetchSessionsPage(
          agentId,
          limit,
        );
        if (_storeAgentId !== agentId) return _sessions;
        applySessionPage(valid, more, limit, agentId, activeThreadId);
        return visibleSessionsForAgent(valid, agentId, activeThreadId);
      } catch {
        return _sessions;
      } finally {
        if (_storeAgentId === agentId) {
          setModuleLoading(false);
        }
      }
    },
    [agentId],
  );

  const loadMoreSessions = useCallback(
    async (activeThreadId?: string) => {
      if (!agentId || _loadingMore || !_hasMore) return;
      setModuleLoadingMore(true);
      try {
        const nextLimit = getLoadedLimit(agentId) + SESSION_PAGE_SIZE;
        const { sessions: valid, hasMore: more } = await fetchSessionsPage(
          agentId,
          nextLimit,
        );
        if (_storeAgentId !== agentId) return;
        applySessionPage(valid, more, nextLimit, agentId, activeThreadId);
      } catch {
        /* ignore */
      } finally {
        setModuleLoadingMore(false);
      }
    },
    [agentId],
  );

  const fetchAllSessions = useCallback(
    async (activeThreadId?: string) => {
      if (!agentId) return;
      try {
        const { sessions: valid, hasMore: more } = await fetchSessionsPage(
          agentId,
          50,
        );
        if (_storeAgentId !== agentId) return;
        applySessionPage(valid, more, valid.length, agentId, activeThreadId);
      } catch {
        /* ignore */
      }
    },
    [agentId],
  );

  const ensureThreadInList = useCallback(
    async (threadId: string): Promise<ThreadProbeResult> => {
      if (!agentId || !threadId) return "missing";
      if (_sessions.some((s) => s.id === threadId)) return "found";
      try {
        const limit = getLoadedLimit(agentId);
        const probeLimit = Math.max(limit + 1, 50);
        const { sessions: valid, hasMore: more } = await fetchSessionsPage(
          agentId,
          probeLimit,
        );
        // Agent switched while the probe was in flight — do not rewrite URL.
        if (_storeAgentId !== agentId) return "unknown";
        const found = valid.some((s) => s.id === threadId);
        if (!found) return "missing";
        applySessionPage(
          valid,
          more || valid.length > limit,
          limit,
          agentId,
          threadId,
        );
        return "found";
      } catch {
        // Network/API failure — keep the URL until a later successful probe.
        return "unknown";
      }
    },
    [agentId],
  );

  // Fetch only: agent switches are synced in-render via syncStoreToAgent.
  useEffect(() => {
    if (!agentId) return;
    resetSessionPagination(agentId);
    setModuleLoading(true);
    void (async () => {
      const requestedAgent = agentId;
      try {
        const { sessions: valid, hasMore: more } = await fetchSessionsPage(
          requestedAgent,
          SESSION_PAGE_SIZE,
        );
        if (_storeAgentId !== requestedAgent) return;
        applySessionPage(valid, more, SESSION_PAGE_SIZE, requestedAgent);
      } catch {
        /* ignore */
      } finally {
        if (_storeAgentId === requestedAgent) {
          setModuleLoading(false);
        }
      }
    })();
  }, [agentId]);

  useEffect(() => {
    return onSessionEvent((event) => {
      if (event.kind !== "sessionDeleted") return;
      const { sessionId } = event;
      setModuleSessions((prev) => prev.filter((s) => s.id !== sessionId));
    });
  }, []);

  const createSession = useCallback((): {
    session: Session;
    resolvedId: Promise<string>;
  } => {
    if (!agentId) {
      const empty: Session = {
        id: "",
        name: "New Chat",
        threadId: "",
        updatedAt: null,
        channelType: "dashboard",
      };
      return { session: empty, resolvedId: Promise.resolve("") };
    }
    const placeholder: Session = {
      id: "__pending__",
      name: "New Chat",
      threadId: "",
      updatedAt: new Date().toISOString(),
      channelType: "dashboard",
    };
    setModuleSessions((prev) => [placeholder, ...prev]);
    const resolvedId = octopThreadsApi
      .create(agentId)
      .then((created) => {
        markPendingThread(created.thread_id);
        const session = toSession({
          thread_id: created.thread_id,
          title: null,
          last_active: Math.floor(Date.now() / 1000),
          channel_type: "dashboard",
        });
        setModuleSessions((prev) => [
          session,
          ...prev.filter((s) => s.id !== "__pending__"),
        ]);
        return created.thread_id;
      })
      .catch(() => {
        setModuleSessions((prev) => prev.filter((s) => s.id !== "__pending__"));
        return "";
      });
    return { session: placeholder, resolvedId };
  }, [agentId]);

  const deleteSession = useCallback(
    async (id: string) => {
      if (!agentId || !id) return false;
      try {
        await octopThreadsApi.delete(agentId, id);
        setModuleSessions((prev) => prev.filter((s) => s.id !== id));
        chatStore.removeSession(id);
        chatStore.emitSessionEvent({ kind: "sessionDeleted", sessionId: id });
        return true;
      } catch {
        return false;
      }
    },
    [agentId],
  );

  const pinSession = useCallback(
    (id: string, pinned: boolean) => {
      setModuleSessions((prev) =>
        sortSessions(prev.map((s) => (s.id === id ? { ...s, pinned } : s))),
      );
      if (agentId) {
        void octopThreadsApi.patch(agentId, id, { pinned }).catch(() => {});
      }
    },
    [agentId],
  );

  const renameSession = useCallback(
    (id: string, name: string) => {
      setModuleSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, name } : s)),
      );
      if (agentId) {
        void octopThreadsApi.rename(agentId, id, name).catch(() => {});
      }
    },
    [agentId],
  );

  const syncSession = useCallback(
    async (localId: string): Promise<string | null> => {
      void localId;
      return null;
    },
    [],
  );

  return {
    sessions,
    loading,
    hasMore,
    loadingMore,
    createSession,
    deleteSession,
    renameSession,
    pinSession,
    fetchSessions,
    loadMoreSessions,
    fetchAllSessions,
    ensureThreadInList,
    syncSession,
  };
}
