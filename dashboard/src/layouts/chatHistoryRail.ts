export const CHAT_HISTORY_RAIL_ID = "octop-chat-history-rail";

export function isChatPath(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}
