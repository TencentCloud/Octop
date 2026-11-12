import { useCallback, useEffect, useMemo, useState } from "react";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import {
  hideExpertId,
  readHiddenExpertIds,
  unhideExpertId,
} from "../utils/hiddenExpertsPrefs";

type ExpertLike = {
  agent_id: string;
};

/**
 * Per-user localStorage preference for hiding experts from chat lists.
 * Pass keepAgentIds only for rows that must stay visible for another reason,
 * such as experts already mentioned in the composer.
 */
export function useHiddenSharedExperts() {
  const userId = useCurrentUser()?.id ?? null;
  const [hiddenIds, setHiddenIds] = useState(() => readHiddenExpertIds(userId));

  useEffect(() => {
    setHiddenIds(readHiddenExpertIds(userId));
  }, [userId]);

  const hide = useCallback(
    (agentId: string) => {
      setHiddenIds(hideExpertId(agentId, userId));
    },
    [userId],
  );

  const unhide = useCallback(
    (agentId: string) => {
      setHiddenIds(unhideExpertId(agentId, userId));
    },
    [userId],
  );

  const isHidden = useCallback(
    (agentId: string) => hiddenIds.has(agentId),
    [hiddenIds],
  );

  const filterVisible = useCallback(
    <T extends ExpertLike>(
      agents: T[],
      options?: { keepAgentIds?: Iterable<string> },
    ): T[] => {
      const keep = new Set(
        options?.keepAgentIds ? [...options.keepAgentIds].filter(Boolean) : [],
      );
      return agents.filter((agent) => {
        if (keep.has(agent.agent_id)) return true;
        return !hiddenIds.has(agent.agent_id);
      });
    },
    [hiddenIds],
  );

  const pickHidden = useCallback(
    <T extends ExpertLike>(agents: T[]): T[] =>
      agents.filter((agent) => hiddenIds.has(agent.agent_id)),
    [hiddenIds],
  );

  const canHide = useCallback(
    (agent: ExpertLike) => agent.agent_id.length > 0,
    [],
  );

  return useMemo(
    () => ({
      hiddenIds,
      hide,
      unhide,
      isHidden,
      filterVisible,
      pickHidden,
      canHide,
    }),
    [hiddenIds, hide, unhide, isHidden, filterVisible, pickHidden, canHide],
  );
}
