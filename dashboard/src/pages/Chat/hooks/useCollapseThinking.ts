import { useLocalStorageState } from "ahooks";

/** Browser-wide display preference, shared by the menu and process panels. */
export function useCollapseThinking() {
  return useLocalStorageState<boolean>("octop:collapse-thinking", {
    defaultValue: false,
    listenStorageChange: true,
  });
}
