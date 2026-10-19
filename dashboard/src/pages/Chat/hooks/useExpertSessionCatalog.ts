import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import type { OctopAgent } from "../../../context/AgentContext";
import { isAgentChatReady } from "../../../utils/agentError";
import { sortSessions, toSession, type Session } from "./useSessions";
import { onSessionEvent } from "./chatStore";

/** How many threads to scan per expert while the nav search box is active. */
const SEARCH_THREAD_LIMIT = 100;

/**
 * Session titles for experts other than the one already loaded in the chat
 * page. Fetches only while search is active.
 */
export function useExpertSessionCatalog(
  agents: readonly OctopAgent[],
  enabled: boolean,
  skipAgentId?: string | null,
  archived = false,
) {
  const [catalog, setCatalog] = useState<{
    archived: boolean;
    byAgent: Record<string, Session[]>;
  }>({ archived, byAgent: {} });
  // Never expose the previous view while its replacement request is in flight.
  const byAgent = catalog.archived === archived ? catalog.byAgent : {};
  const [loading, setLoading] = useState(false);
  const removedWhileLoading = useRef(new Set<string>());
  const agentKey = useMemo(
    () =>
      agents
        .filter(
          (agent) =>
            agent.agent_id !== skipAgentId && isAgentChatReady(agent.state),
        )
        .map((agent) => agent.agent_id)
        .sort()
        .join(","),
    [agents, skipAgentId],
  );

  useEffect(() => {
    if (!enabled || !agentKey) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const removedIds = new Set<string>();
    removedWhileLoading.current = removedIds;
    setLoading(true);
    const ids = agentKey.split(",").filter(Boolean);
    void Promise.all(
      ids.map(async (id) => {
        try {
          const rows = await octopThreadsApi.list(
            id,
            SEARCH_THREAD_LIMIT,
            archived,
          );
          return [id, sortSessions(rows.map(toSession))] as const;
        } catch {
          return [id, [] as Session[]] as const;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      setCatalog({
        archived,
        byAgent: Object.fromEntries(
          entries.map(([id, sessions]) => [
            id,
            sessions.filter((session) => !removedIds.has(session.id)),
          ]),
        ),
      });
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, agentKey, archived]);

  useEffect(
    () =>
      onSessionEvent((event) => {
        if (event.kind !== "sessionDeleted") return;
        removedWhileLoading.current.add(event.sessionId);
        setCatalog((prev) => ({
          ...prev,
          byAgent: Object.fromEntries(
            Object.entries(prev.byAgent).map(([id, sessions]) => [
              id,
              sessions.filter((session) => session.id !== event.sessionId),
            ]),
          ),
        }));
      }),
    [],
  );

  const patch = useCallback(
    (agentId: string, updater: (prev: Session[]) => Session[]) => {
      setCatalog((prev) =>
        prev.archived !== archived
          ? prev
          : {
              ...prev,
              byAgent: {
                ...prev.byAgent,
                [agentId]: sortSessions(updater(prev.byAgent[agentId] ?? [])),
              },
            },
      );
    },
    [archived],
  );

  return { byAgent, loading, patch };
}
