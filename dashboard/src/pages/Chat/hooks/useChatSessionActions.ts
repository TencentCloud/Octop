import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY } from "../constants";
import { pickPreferredSession, toSession, type Session } from "./useSessions";

interface UseChatSessionActionsParams {
  resolvedAgentId: string | null | undefined;
  activeThreadId: string | null;
  sessions: Session[];
  isMobile: boolean;
  setActiveAgent: (id: string) => void;
  setSidebarOpen: (open: boolean) => void;
  setSelectedModel: (model: string | null) => void;
  setHasBrowserTool: (value: boolean) => void;
  deleteSession: (id: string) => Promise<boolean>;
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

  const handleNewChat = useCallback(() => {
    setSelectedModel(null);
    setHasBrowserTool(false);
    const agent = resolvedAgentId;
    if (!agent) return;
    navigate(`/chat/${agent}`);
  }, [navigate, resolvedAgentId, setSelectedModel, setHasBrowserTool]);

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
    async (id: string) => {
      const deleted = await deleteSession(id);
      if (!deleted) return;
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
    handleSelectSession,
    navigateToAgent,
    handleDeleteSession,
  };
}
