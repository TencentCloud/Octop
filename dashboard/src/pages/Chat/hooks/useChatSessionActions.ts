import { useChatRoute } from "../../../hooks/useChatRoute";
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
  const { chatPath } = useChatRoute();

  const handleNewChat = useCallback(() => {
    setSelectedModel(null);
    setHasBrowserTool(false);
    const agent = resolvedAgentId;
    if (!agent) return;
    navigate(chatPath(agent));
  }, [
    navigate,
    chatPath,
    resolvedAgentId,
    setSelectedModel,
    setHasBrowserTool,
  ]);

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
      navigate(chatPath(agentId));
      chatStore.clearMessages(EMPTY_CHAT_SESSION_KEY);
      if (isMobile) setSidebarOpen(false);
    },
    [
      navigate,
      chatPath,
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
      navigate(chatPath(agent, id));
      if (isMobile) setSidebarOpen(false);
    },
    [
      activeThreadId,
      navigate,
      chatPath,
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
      navigate(chatPath(agentId), { replace: true });
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
            navigate(chatPath(agentId, preferred.id), { replace: true });
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
      chatPath,
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
          navigate(chatPath(agent, preferred.id), { replace: true });
        } else {
          navigate(chatPath(agent), { replace: true });
          clearMessages();
        }
      }
    },
    [
      activeThreadId,
      sessions,
      deleteSession,
      navigate,
      chatPath,
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
  };
}
