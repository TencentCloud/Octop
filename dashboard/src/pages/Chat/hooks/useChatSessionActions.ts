import { useCallback, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY, isTemporaryThreadId } from "../constants";
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
  deleteSession: (id: string, compact: boolean) => Promise<boolean | null>;
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
  const { pathname } = useLocation();
  const pendingAgentSelection = useRef<{ pathname: string } | null>(null);

  useLayoutEffect(() => {
    if (pendingAgentSelection.current?.pathname !== pathname) {
      pendingAgentSelection.current = null;
    }
  }, [pathname]);

  useLayoutEffect(
    () => () => {
      pendingAgentSelection.current = null;
    },
    [],
  );

  const handleNewChat = useCallback(() => {
    setSelectedModel(null);
    setHasBrowserTool(false);
    const agent = resolvedAgentId;
    if (!agent) return;
    pendingAgentSelection.current = null;
    markInitialNavDone(agent);
    navigate(`/chat/${agent}`);
  }, [
    navigate,
    resolvedAgentId,
    setSelectedModel,
    setHasBrowserTool,
    markInitialNavDone,
  ]);

  /**
   * New chat with an arbitrary expert. Unlike {@link navigateToAgent} this stays
   * on the empty-chat view instead of jumping to that expert's latest thread.
   */
  const handleNewChatWithAgent = useCallback(
    (agentId: string) => {
      if (!agentId) return;
      pendingAgentSelection.current = null;
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
      pendingAgentSelection.current = null;
      setSelectedModel(null);
      if (!isTemporaryThreadId(id)) {
        void octopThreadsApi.rebind(agent, id).catch(() => {});
      }
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
      const selection = { pathname: `/chat/${agentId}` };
      pendingAgentSelection.current = selection;
      resetNavForAgentSwitch();
      navigate(selection.pathname, { replace: true });
      setActiveAgent(agentId);
      // We land on the new-chat view, so only that session is stale here.
      // Clearing the thread we are leaving would drop an in-flight turn.
      chatStore.clearMessages(EMPTY_CHAT_SESSION_KEY);
      if (isMobile) setSidebarOpen(false);

      void (async () => {
        try {
          const rows = await octopThreadsApi.list(agentId);
          if (pendingAgentSelection.current !== selection) return;
          const preferred = pickPreferredSession(rows.map(toSession));
          markInitialNavDone(agentId);
          if (preferred) {
            void octopThreadsApi.rebind(agentId, preferred.id).catch(() => {});
            navigate(`/chat/${agentId}/${preferred.id}`, { replace: true });
          }
        } catch {
          /* initialNav effect picks thread once sessions load */
        } finally {
          if (pendingAgentSelection.current === selection) {
            pendingAgentSelection.current = null;
          }
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
      if (deleted !== true) return deleted;
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
  };
}
