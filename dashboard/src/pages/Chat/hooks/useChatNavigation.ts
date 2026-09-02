import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { octopAgentsApi } from "../../../api/modules/octopAgents";
import * as chatStore from "./chatStore";
import {
  pickPreferredSession,
  isPendingThread,
  clearPendingThread,
  clearSessionUnread,
  type Session,
  type ThreadProbeResult,
} from "./useSessions";
import { EMPTY_CHAT_SESSION_KEY } from "../constants";

interface UseChatNavigationParams {
  routeAgentId: string | undefined;
  threadId: string | undefined;
  resolvedAgentId: string | null | undefined;
  activeThreadId: string | null;
  sessions: Session[];
  sessionsLoading: boolean;
  prefillInputRef: React.MutableRefObject<string>;
  loadHistory: (
    threadId: string,
    opts?: { force?: boolean },
  ) => Promise<void>;
  clearMessages: () => void;
  ensureThreadInList: (threadId: string) => Promise<ThreadProbeResult>;
  fetchSessions: (activeId?: string) => Promise<Session[]>;
  refreshAgents: (opts?: { silent?: boolean }) => Promise<void>;
}

export function useChatNavigation({
  routeAgentId,
  threadId,
  resolvedAgentId,
  activeThreadId,
  sessions,
  sessionsLoading,
  prefillInputRef,
  loadHistory,
  clearMessages,
  ensureThreadInList,
  fetchSessions,
  refreshAgents,
}: UseChatNavigationParams) {
  const navigate = useNavigate();

  const weixinHydrateKeyRef = useRef<string | null>(null);
  const activeChannelType = sessions.find(
    (s) => s.id === activeThreadId,
  )?.channelType;

  useEffect(() => {
    if (!resolvedAgentId) return;
    if (activeThreadId) {
      if (isPendingThread(activeThreadId)) return;
      if (sessionsLoading && !activeChannelType) return;
      const visitKey = `${resolvedAgentId}:${activeThreadId}`;
      const forceWeixin =
        activeChannelType === "weixin" &&
        weixinHydrateKeyRef.current !== visitKey;
      if (forceWeixin) weixinHydrateKeyRef.current = visitKey;
      if (activeChannelType && activeChannelType !== "weixin") {
        weixinHydrateKeyRef.current = null;
      }
      void loadHistory(activeThreadId, { force: forceWeixin });
    } else {
      weixinHydrateKeyRef.current = null;
      const emptySnap = chatStore.getSnapshot(EMPTY_CHAT_SESSION_KEY);
      if (emptySnap.messages.length === 0 && !emptySnap.isStreaming) {
        clearMessages();
      }
    }
  }, [
    activeThreadId,
    resolvedAgentId,
    loadHistory,
    clearMessages,
    activeChannelType,
    sessionsLoading,
  ]);

  const markedAgentReadRef = useRef<string | null>(null);
  useEffect(() => {
    if (!resolvedAgentId) return;
    if (markedAgentReadRef.current === resolvedAgentId) return;
    markedAgentReadRef.current = resolvedAgentId;
    void octopAgentsApi
      .markRead(resolvedAgentId)
      .then(() => refreshAgents({ silent: true }))
      .catch(() => {});
  }, [resolvedAgentId, refreshAgents]);

  useEffect(() => {
    if (!resolvedAgentId || !activeThreadId || isPendingThread(activeThreadId)) {
      return;
    }
    const session = sessions.find((s) => s.id === activeThreadId);
    if (!session || session.channelType !== "weixin") return;
    if (!(session.unreadCount ?? 0)) return;
    void octopThreadsApi
      .markRead(resolvedAgentId, activeThreadId)
      .then(() => {
        clearSessionUnread(activeThreadId);
        void refreshAgents({ silent: true });
      })
      .catch(() => {});
  }, [resolvedAgentId, activeThreadId, sessions, refreshAgents]);

  useEffect(() => {
    const refreshBadges = () => void refreshAgents({ silent: true });
    refreshBadges();
    const intervalId = window.setInterval(refreshBadges, 10_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") refreshBadges();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refreshAgents]);

  useEffect(() => {
    return chatStore.onStreamEvent((event) => {
      if (
        event.kind === "streamEnd" &&
        event.sessionId === (activeThreadId ?? "")
      ) {
        void fetchSessions(activeThreadId ?? undefined);
      }
    });
  }, [activeThreadId, fetchSessions]);

  const initialNavDone = useRef<string | null>(null);
  const chatUrlStateRef = useRef<{ agentId?: string; threadId?: string }>({});

  useEffect(() => {
    const prev = chatUrlStateRef.current;
    if (
      routeAgentId &&
      prev.agentId &&
      prev.agentId !== routeAgentId &&
      threadId &&
      threadId === prev.threadId
    ) {
      initialNavDone.current = null;
      navigate(`/chat/${routeAgentId}`, { replace: true });
      clearMessages();
    }
    chatUrlStateRef.current = { agentId: routeAgentId, threadId };
  }, [routeAgentId, threadId, navigate, clearMessages]);

  useEffect(() => {
    if (sessionsLoading || prefillInputRef.current) return;
    const agent = resolvedAgentId;
    if (!agent) return;
    if (threadId) {
      initialNavDone.current = agent;
      return;
    }
    if (initialNavDone.current === agent) return;
    initialNavDone.current = agent;
    if (sessions.length > 0) {
      const preferred = pickPreferredSession(sessions);
      if (preferred) {
        void octopThreadsApi.rebind(agent, preferred.id).catch(() => {});
        navigate(`/chat/${agent}/${preferred.id}`, { replace: true });
      }
    } else if (!routeAgentId) {
      navigate(`/chat/${agent}`, { replace: true });
    }
  }, [
    sessions,
    sessionsLoading,
    threadId,
    resolvedAgentId,
    routeAgentId,
    navigate,
    prefillInputRef,
  ]);

  const ensureThreadAttemptRef = useRef<string | null>(null);
  useEffect(() => {
    ensureThreadAttemptRef.current = null;
  }, [resolvedAgentId]);

  useEffect(() => {
    if (!resolvedAgentId || !threadId || sessionsLoading) return;
    if (isPendingThread(threadId)) {
      if (sessions.some((s) => s.id === threadId)) {
        clearPendingThread(threadId);
      }
      return;
    }
    if (sessions.some((s) => s.id === threadId)) {
      ensureThreadAttemptRef.current = null;
      return;
    }
    // Thread missing from the visible page (or list is empty after load).
    // Probe the API — only rewrite the URL when the probe confirms absence.
    // Do not treat a still-loading / failed list as "deleted".
    const attemptKey = `${resolvedAgentId}:${threadId}`;
    if (ensureThreadAttemptRef.current === attemptKey) {
      return;
    }
    ensureThreadAttemptRef.current = attemptKey;
    void ensureThreadInList(threadId).then((result) => {
      if (ensureThreadAttemptRef.current !== attemptKey) return;
      // Only rewrite when the probe confirms absence — keep URL on found/unknown.
      if (result !== "missing") return;
      const preferred = pickPreferredSession(sessions);
      if (preferred) {
        void octopThreadsApi
          .rebind(resolvedAgentId, preferred.id)
          .catch(() => {});
        navigate(`/chat/${resolvedAgentId}/${preferred.id}`, { replace: true });
      } else {
        navigate(`/chat/${resolvedAgentId}`, { replace: true });
      }
    });
  }, [
    resolvedAgentId,
    threadId,
    sessions,
    sessionsLoading,
    navigate,
    ensureThreadInList,
  ]);

  const resetNavForAgentSwitch = () => {
    initialNavDone.current = null;
    ensureThreadAttemptRef.current = null;
  };

  const markInitialNavDone = (agentId: string) => {
    initialNavDone.current = agentId;
  };

  return { resetNavForAgentSwitch, markInitialNavDone };
}
