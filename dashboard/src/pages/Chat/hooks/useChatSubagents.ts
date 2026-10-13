import { useEffect, useState } from "react";
import {
  listAgentSubagents,
  type AgentSubagentSummary,
} from "../../../api/modules/subagents";

/** Installed workspace subagents for the running chat agent (empty if not ready). */
export function useChatSubagents(
  agentId: string | null,
): AgentSubagentSummary[] {
  const [subagents, setSubagents] = useState<AgentSubagentSummary[]>([]);

  useEffect(() => {
    if (!agentId) {
      setSubagents([]);
      return;
    }
    let cancelled = false;
    void listAgentSubagents(agentId)
      .then((rows) => {
        if (!cancelled) setSubagents(rows);
      })
      .catch(() => {
        if (!cancelled) setSubagents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  return subagents;
}
