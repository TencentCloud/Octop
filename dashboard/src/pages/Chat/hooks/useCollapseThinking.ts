import { useLocalStorageState } from "ahooks";

/** Solo / 1:1 chat preference (default: expand while streaming). */
export const COLLAPSE_THINKING_SOLO_KEY = "octop:collapse-thinking";
/** Team room preference (default: collapse while streaming). */
export const COLLAPSE_THINKING_TEAM_KEY = "octop:collapse-thinking:team";

export function collapseThinkingStorageKey(isTeam: boolean): string {
  return isTeam ? COLLAPSE_THINKING_TEAM_KEY : COLLAPSE_THINKING_SOLO_KEY;
}

/**
 * Browser display preference for folding thinking/tool panels while streaming.
 * Team and solo chats use separate keys so toggling one does not affect the other.
 */
export function useCollapseThinking(isTeam = false) {
  return useLocalStorageState<boolean>(collapseThinkingStorageKey(isTeam), {
    defaultValue: isTeam,
    listenStorageChange: true,
  });
}
