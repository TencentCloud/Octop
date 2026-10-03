import { useCallback } from "react";
import { useLocation } from "react-router-dom";
import { isEmbeddedChatPath } from "../utils/chatRoute";

export function useChatRoute() {
  const { pathname } = useLocation();
  const embedded = isEmbeddedChatPath(pathname);
  const chatPath = useCallback(
    (agentId: string, threadId?: string) => {
      const base = embedded ? "/embed/chat" : "/chat";
      return `${base}/${agentId}${threadId ? `/${threadId}` : ""}`;
    },
    [embedded],
  );
  return { embedded, chatPath };
}
