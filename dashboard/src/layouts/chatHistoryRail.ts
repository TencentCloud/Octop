export const CHAT_HISTORY_RAIL_ID = "octop-chat-history-rail";

/** Open mobile/desktop nav on the minimal-mode records pane. */
export const OPEN_NAV_RECORDS_EVENT = "octop:open-nav-records";

export function isChatPath(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}

export { isGroupedNavKey as isSettingsPaneNavKey } from "./sidebarNav";
