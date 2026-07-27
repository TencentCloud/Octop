import { useEffect, useState } from "react";
import { CHAT_HISTORY_RAIL_ID } from "../../../layouts/chatHistoryRail";

/** DOM mount for the session-history rail (sibling of app nav, not inside page content). */
export function useChatHistoryRail(): HTMLElement | null {
  const [rail, setRail] = useState<HTMLElement | null>(() =>
    typeof document !== "undefined"
      ? document.getElementById(CHAT_HISTORY_RAIL_ID)
      : null,
  );

  useEffect(() => {
    setRail(document.getElementById(CHAT_HISTORY_RAIL_ID));
  }, []);

  return rail;
}
