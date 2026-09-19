import { useCallback, useEffect, useMemo, useState } from "react";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { isSharedExpertViewer } from "../../../utils/sharedExpert";
import {
  hideExpertId,
  readHiddenExpertIds,
  unhideExpertId,
} from "../utils/hiddenExpertsPrefs";

type ExpertLike = {
  agent_id: string;
  is_shared?: boolean;
  is_owner?: boolean;
};

/**
 * Per-user localStorage preference for hiding shared experts from chat lists.
 * Owned experts are never treated as hideable via this hook.
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
        if (!isSharedExpertViewer(agent)) return true;
        if (keep.has(agent.agent_id)) return true;
        return !hiddenIds.has(agent.agent_id);
      });
    },
    [hiddenIds],
  );

  const pickHidden = useCallback(
    <T extends ExpertLike>(agents: T[]): T[] =>
      agents.filter(
        (agent) => isSharedExpertViewer(agent) && hiddenIds.has(agent.agent_id),
      ),
    [hiddenIds],
  );

  const canHide = useCallback(
    (agent: ExpertLike) => isSharedExpertViewer(agent),
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
