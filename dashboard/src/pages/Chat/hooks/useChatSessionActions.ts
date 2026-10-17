import { useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY } from "../constants";
import {
  deleteSessions,
  pickPreferredSession,
  toSession,
  type Session,
} from "./useSessions";

interface UseChatSessionActionsParams {
  resolvedAgentId: string | null | undefined;
  activeThreadId: string | null;
  sessions: Session[];
  isMobile: boolean;
  setActiveAgent: (id: string) => void;
  setSidebarOpen: (open: boolean) => void;
  setSelectedModel: (model: string | null) => void;
  setHasBrowserTool: (value: boolean) => void;
  deleteSession: (id: string, compact: boolean) => Promise<boolean>;
  clearMessages: () => void;
  resetNavForAgentSwitch: () => void;
  markInitialNavDone: (agentId: string) => void;
}

export function useChatSessionActions({
  resolvedAgentId,
  activeThreadId,
  sessions,
  isMobile,
  setActiveAgent,
  setSidebarOpen,
  setSelectedModel,
  setHasBrowserTool,
  deleteSession,
  clearMessages,
  resetNavForAgentSwitch,
  markInitialNavDone,
}: UseChatSessionActionsParams) {
  const navigate = useNavigate();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const latest = useRef({
    resolvedAgentId,
    activeThreadId,
    sessions,
    clearMessages,
  });
  latest.current = { resolvedAgentId, activeThreadId, sessions, clearMessages };

  const handleBatchDeleteSessions = useCallback(
    async (agentId: string, ids: string[]) => {
      const result = await deleteSessions(agentId, ids);
      if (!mounted.current) return result;
      const current = latest.current;
      // A batch may finish after the user has switched experts or conversations.
      if (
        current.resolvedAgentId === agentId &&
        current.activeThreadId &&
        result.deletedIds.includes(current.activeThreadId)
      ) {
        const deleted = new Set(result.deletedIds);
        const preferred = pickPreferredSession(
          current.sessions.filter((s) => !deleted.has(s.id)),
        );
        navigate(
          preferred ? `/chat/${agentId}/${preferred.id}` : `/chat/${agentId}`,
          { replace: true },
        );
        if (!preferred) current.clearMessages();
      }
      return result;
    },
    [navigate],
  );

  const handleNewChat = useCallback(() => {
    setSelectedModel(null);
    setHasBrowserTool(false);
    const agent = resolvedAgentId;
    if (!agent) return;
    navigate(`/chat/${agent}`);
  }, [navigate, resolvedAgentId, setSelectedModel, setHasBrowserTool]);

  /**
   * New chat with an arbitrary expert. Unlike {@link navigateToAgent} this stays
   * on the empty-chat view instead of jumping to that expert's latest thread.
   */
  const handleNewChatWithAgent = useCallback(
    (agentId: string) => {
      if (!agentId) return;
      setSelectedModel(null);
      setHasBrowserTool(false);
      if (agentId !== resolvedAgentId) {
        resetNavForAgentSwitch();
        setActiveAgent(agentId);
      }
      markInitialNavDone(agentId);
      navigate(`/chat/${agentId}`);
      chatStore.clearMessages(EMPTY_CHAT_SESSION_KEY);
      if (isMobile) setSidebarOpen(false);
    },
    [
      navigate,
      resolvedAgentId,
      isMobile,
      setActiveAgent,
      setSidebarOpen,
      setSelectedModel,
      setHasBrowserTool,
      resetNavForAgentSwitch,
      markInitialNavDone,
    ],
  );

  const handleSelectSession = useCallback(
    (id: string) => {
      const agent = resolvedAgentId;
      if (!agent) return;
      if (id === activeThreadId) return;
      setSelectedModel(null);
      void octopThreadsApi.rebind(agent, id).catch(() => {});
      navigate(`/chat/${agent}/${id}`);
      if (isMobile) setSidebarOpen(false);
    },
    [
      activeThreadId,
      navigate,
      isMobile,
      resolvedAgentId,
      setSidebarOpen,
      setSelectedModel,
    ],
  );

  const navigateToAgent = useCallback(
    (agentId: string) => {
      if (!agentId) return;
      resetNavForAgentSwitch();
      navigate(`/chat/${agentId}`, { replace: true });
      setActiveAgent(agentId);
      // We land on the new-chat view, so only that session is stale here.
      // Clearing the thread we are leaving would drop an in-flight turn.
      chatStore.clearMessages(EMPTY_CHAT_SESSION_KEY);
      if (isMobile) setSidebarOpen(false);

      void (async () => {
        try {
          const rows = await octopThreadsApi.list(agentId);
          const preferred = pickPreferredSession(rows.map(toSession));
          if (preferred) {
            markInitialNavDone(agentId);
            void octopThreadsApi.rebind(agentId, preferred.id).catch(() => {});
            navigate(`/chat/${agentId}/${preferred.id}`, { replace: true });
          } else {
            markInitialNavDone(agentId);
          }
        } catch {
          /* initialNav effect picks thread once sessions load */
        }
      })();
    },
    [
      setActiveAgent,
      navigate,
      isMobile,
      setSidebarOpen,
      resetNavForAgentSwitch,
      markInitialNavDone,
    ],
  );

  const handleDeleteSession = useCallback(
    async (id: string, compact: boolean) => {
      const deleted = await deleteSession(id, compact);
      if (!deleted) return false;
      const agent = resolvedAgentId;
      if (id === activeThreadId && agent) {
        const remaining = sessions.filter((s) => s.id !== id);
        const preferred = pickPreferredSession(remaining);
        if (preferred) {
          navigate(`/chat/${agent}/${preferred.id}`, { replace: true });
        } else {
          navigate(`/chat/${agent}`, { replace: true });
          clearMessages();
        }
      }
      return true;
    },
    [
      activeThreadId,
      sessions,
      deleteSession,
      navigate,
      clearMessages,
      resolvedAgentId,
    ],
  );

  return {
    handleNewChat,
    handleNewChatWithAgent,
    handleSelectSession,
    navigateToAgent,
    handleDeleteSession,
    handleBatchDeleteSessions,
  };
}
