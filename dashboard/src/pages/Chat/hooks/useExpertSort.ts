import { useCallback, useEffect, useState } from "react";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import {
  readExpertSortMode,
  writeExpertSortMode,
  type ExpertSortMode,
} from "../utils/pinnedExpertsPrefs";

/** Per-user chat-nav sort, shared by the classic and minimal sidebars. */
export function useExpertSort() {
  const userId = useCurrentUser()?.id ?? null;
  const [mode, setModeState] = useState<ExpertSortMode>(() =>
    readExpertSortMode(userId),
  );

  useEffect(() => {
    setModeState(readExpertSortMode(userId));
  }, [userId]);

  const setMode = useCallback(
    (next: ExpertSortMode) => {
      setModeState(writeExpertSortMode(next, userId));
    },
    [userId],
  );

  return { mode, setMode };
}
