import { useSyncExternalStore } from "react";
import * as chatStore from "./chatStore";
import type { ChatMessage } from "./useChat";

/** Live tool message row for a ``toolData.callId`` in the active thread. */
export function useToolMessageByCallId(
  threadId: string | null,
  callId: string,
): ChatMessage | null {
  return useSyncExternalStore(
    (onStoreChange) =>
      threadId ? chatStore.subscribe(threadId, onStoreChange) : () => {},
    () => {
      if (!threadId) return null;
      const { messages } = chatStore.getSnapshot(threadId);
      return (
        messages.find(
          (m) => m.toolData?.callId === callId && m.toolData != null,
        ) ?? null
      );
    },
    () => null,
  );
}
