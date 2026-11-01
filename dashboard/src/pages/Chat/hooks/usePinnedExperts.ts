import { useCallback, useEffect, useState } from "react";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import {
  readPinnedExpertIds,
  togglePinnedExpertId,
} from "../utils/pinnedExpertsPrefs";

/** Per-user pin order for the chat expert nav (classic and minimal). */
export function usePinnedExperts() {
  const userId = useCurrentUser()?.id ?? null;
  const [pinnedIds, setPinnedIds] = useState(() => readPinnedExpertIds(userId));

  useEffect(() => {
    setPinnedIds(readPinnedExpertIds(userId));
  }, [userId]);

  const togglePin = useCallback(
    (agentId: string) => {
      setPinnedIds(togglePinnedExpertId(agentId, userId));
    },
    [userId],
  );

  const isPinned = useCallback(
    (agentId: string) => pinnedIds.includes(agentId),
    [pinnedIds],
  );

  return { pinnedIds, togglePin, isPinned };
}
