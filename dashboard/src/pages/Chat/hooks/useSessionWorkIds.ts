import { useEffect, useState } from "react";
import { onStreamEvent } from "./chatStore";

/** Thread ids whose turn is streaming in this tab (start/resume until end). */
export function useSessionWorkIds(): ReadonlySet<string> {
  const [ids, setIds] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(() => {
    return onStreamEvent((event) => {
      setIds((prev) => {
        const busy = event.kind !== "streamEnd";
        if (busy === prev.has(event.sessionId)) return prev;
        const next = new Set(prev);
        if (busy) next.add(event.sessionId);
        else next.delete(event.sessionId);
        return next;
      });
    });
  }, []);

  return ids;
}
