import { useCallback, useEffect, useMemo, useState } from "react";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import type { OctopAgent } from "../../../context/AgentContext";
import { isAgentChatReady } from "../../../utils/agentError";
import { sortSessions, toSession, type Session } from "./useSessions";

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
) {
  const [byAgent, setByAgent] = useState<Record<string, Session[]>>({});
  const [loading, setLoading] = useState(false);
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
    setLoading(true);
    const ids = agentKey.split(",").filter(Boolean);
    void Promise.all(
      ids.map(async (id) => {
        try {
          const rows = await octopThreadsApi.list(id, SEARCH_THREAD_LIMIT);
          return [id, sortSessions(rows.map(toSession))] as const;
        } catch {
          return [id, [] as Session[]] as const;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      setByAgent(Object.fromEntries(entries));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, agentKey]);

  const patch = useCallback(
    (agentId: string, updater: (prev: Session[]) => Session[]) => {
      setByAgent((prev) => ({
        ...prev,
        [agentId]: sortSessions(updater(prev[agentId] ?? [])),
      }));
    },
    [],
  );

  return { byAgent, loading, patch };
}
