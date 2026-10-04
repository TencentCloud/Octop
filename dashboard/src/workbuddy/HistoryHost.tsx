import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { useAgent } from "../context/AgentContext";
import { useSessions } from "../pages/Chat/hooks/useSessions";
import SessionList from "../pages/Chat/components/SessionList";
import { octopThreadsApi } from "../api/modules/octopThreads";
import { apiErrorMessage } from "../utils/apiError";

/** Non-chat routes subscribe to the same session store; Chat owns the live history while mounted. */
export default function HistoryHost() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { agents, activeAgentId, setActiveAgent } = useAgent();
  const {
    sessions,
    hasMore,
    loadingMore,
    loadMoreSessions,
    fetchAllSessions,
    deleteSession,
    renameSession,
    pinSession,
  } = useSessions(activeAgentId);
  const select = (threadId: string, agentId: string) => {
    setActiveAgent(agentId);
    navigate(`/chat/${agentId}/${threadId}`);
  };
  return (
    <SessionList
      agents={agents}
      sessions={sessions}
      activeId={null}
      activeAgentId={activeAgentId}
      hasMore={hasMore}
      loadingMore={loadingMore}
      onLoadMore={() => void loadMoreSessions()}
      onFetchAllSessions={() => void fetchAllSessions()}
      onSelect={select}
      onAgentSelect={(id) => {
        setActiveAgent(id);
        navigate(`/chat/${id}`);
      }}
      onNewChat={(id) => {
        setActiveAgent(id);
        navigate("/home", { state: { newChat: true } });
      }}
      onDelete={(id) => void deleteSession(id)}
      onRename={(id, name) => void renameSession(id, name)}
      onPin={(id, pinned) => void pinSession(id, pinned)}
      onFork={(id) => {
        if (activeAgentId)
          void octopThreadsApi
            .fork(activeAgentId, id, { assistant_turns_from_end: 1 })
            .then((row) => select(row.thread_id, activeAgentId))
            .catch((error) =>
              message.error(apiErrorMessage(error, t("chat.forkFailed"), t)),
            );
      }}
    />
  );
}
