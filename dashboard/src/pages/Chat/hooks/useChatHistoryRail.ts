import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { CHAT_HISTORY_RAIL_ID } from "../../../layouts/chatHistoryRail";
import { useLayoutMode } from "../../../context/LayoutModeContext";

/** DOM mount for the session-history rail (classic sibling rail or minimal nav pane). */
export function useChatHistoryRail(): HTMLElement | null {
  const { layoutMode, minimalPane } = useLayoutMode();
  const { pathname } = useLocation();
  const [rail, setRail] = useState<HTMLElement | null>(() =>
    typeof document !== "undefined"
      ? document.getElementById(CHAT_HISTORY_RAIL_ID)
      : null,
  );

  useEffect(() => {
    const sync = () => {
      setRail(document.getElementById(CHAT_HISTORY_RAIL_ID));
    };
    sync();
    // Layout mode / pane / route swaps remount or clear the rail after paint.
    const raf = window.requestAnimationFrame(sync);
    const t = window.setTimeout(sync, 0);
    return () => {
      window.cancelAnimationFrame(raf);
      window.clearTimeout(t);
    };
  }, [layoutMode, minimalPane, pathname]);

  return rail;
}
