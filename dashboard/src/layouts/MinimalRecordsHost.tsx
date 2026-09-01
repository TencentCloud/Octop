import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { message as antMessage } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";
import { useAgent, selectEnabledExperts } from "../context/AgentContext";
import { octopThreadsApi } from "../api/modules/octopThreads";
import { apiErrorMessage } from "../utils/apiError";
import MinimalAgentSessionNav from "../pages/Chat/components/MinimalAgentSessionNav";
import { emitSessionEvent } from "../pages/Chat/hooks/chatStore";
import { formatThreadTitle } from "../pages/Chat/utils/threadTitle";

function parseChatPath(pathname: string): {
  agentId: string | null;
  threadId: string | null;
} {
  const match = pathname.match(/^\/chat\/([^/]+)(?:\/([^/]+))?/);
  if (!match) return { agentId: null, threadId: null };
  return { agentId: match[1] ?? null, threadId: match[2] ?? null };
}

/**
 * Minimal-layout records pane host for non-chat routes (e.g. /experts).
 * On /chat, Chat portals {@link MinimalAgentSessionNav} with live sessions into
 * the same rail mount instead.
 */
export default function MinimalRecordsHost() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { agents, activeAgentId, setActiveAgent } = useAgent();

  const { agentId: pathAgentId, threadId: pathThreadId } = useMemo(
    () => parseChatPath(location.pathname),
    [location.pathname],
  );
  const resolvedAgentId = pathAgentId ?? activeAgentId;

  // Match the chat page sidebar: only "enabled" (running) experts show in
  // the records pane. A disabled expert (including one stored in
  // localStorage as the last-active) is hidden so the user only sees experts
  // they can actually chat with right now. ``/experts`` itself still lists
  // every expert so users can re-enable the stopped one there.
  const enabledAgents = useMemo(
    () => selectEnabledExperts(agents, resolvedAgentId, { pinActive: false }),
    [agents, resolvedAgentId],
  );

  const handleSelect = useCallback(
    (sessionId: string, agentId: string) => {
      setActiveAgent(agentId);
      navigate(`/chat/${agentId}/${sessionId}`);
    },
    [navigate, setActiveAgent],
  );

  const handleAgentSelect = useCallback(
    (agentId: string) => {
      setActiveAgent(agentId);
      navigate(`/chat/${agentId}`);
    },
    [navigate, setActiveAgent],
  );

  const handleDeleteActive = useCallback(
    async (sessionId: string) => {
      if (!resolvedAgentId || !sessionId) return;
      try {
        await octopThreadsApi.delete(resolvedAgentId, sessionId);
        emitSessionEvent({ kind: "sessionDeleted", sessionId });
        if (pathThreadId === sessionId) {
          navigate(`/chat/${resolvedAgentId}`, { replace: true });
        }
      } catch (error) {
        antMessage.error(apiErrorMessage(error, t("common.deleteFailed"), t));
      }
    },
    [navigate, pathThreadId, resolvedAgentId, t],
  );

  const handleRenameActive = useCallback(
    (sessionId: string, name: string) => {
      if (!resolvedAgentId) return;
      const next = formatThreadTitle(name) || name.trim();
      if (!next) return;
      void octopThreadsApi
        .rename(resolvedAgentId, sessionId, next)
        .catch(() => {});
    },
    [resolvedAgentId],
  );

  const handlePinActive = useCallback(
    (sessionId: string, pinned: boolean) => {
      if (!resolvedAgentId) return;
      void octopThreadsApi
        .patch(resolvedAgentId, sessionId, { pinned })
        .catch(() => {});
    },
    [resolvedAgentId],
  );

  const handleFork = useCallback(
    async (threadId: string, agentId?: string | null) => {
      const agent = agentId || resolvedAgentId;
      if (!agent || !threadId) return;
      try {
        const created = await octopThreadsApi.fork(agent, threadId, {
          assistant_turns_from_end: 1,
        });
        setActiveAgent(agent);
        navigate(`/chat/${agent}/${created.thread_id}`);
      } catch (error) {
        antMessage.error(apiErrorMessage(error, t("chat.forkFailed"), t));
      }
    },
    [navigate, resolvedAgentId, setActiveAgent, t],
  );

  return (
    <MinimalAgentSessionNav
      agents={enabledAgents}
      activeId={pathThreadId}
      activeAgentId={resolvedAgentId}
      activeSessions={[]}
      onSelect={handleSelect}
      onAgentSelect={handleAgentSelect}
      onDeleteActive={(id) => void handleDeleteActive(id)}
      onRenameActive={handleRenameActive}
      onPinActive={handlePinActive}
      onFork={(id, agentId) => void handleFork(id, agentId)}
    />
  );
}
