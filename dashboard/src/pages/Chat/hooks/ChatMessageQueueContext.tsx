import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
  type ReactNode,
} from "react";
import * as chatStore from "./chatStore";
import type { QueuedChatItem } from "./useChatMessageQueue";

type Queues = Record<string, QueuedChatItem[]>;
type StreamEndListener = (sessionId: string) => void;
export const ChatMessageQueueContext = createContext<{
  queues: Queues;
  setQueues: Dispatch<SetStateAction<Queues>>;
  subscribeStreamEnd: (
    listener: StreamEndListener,
    cancelPending?: () => void,
  ) => () => void;
} | null>(null);

/** Authenticated workspace owns the queue; logout unmounts it and removes the subscription. */
export function ChatMessageQueueProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [queues, setQueues] = useState<Queues>({});
  const listener = useRef<StreamEndListener | null>(null);
  const release = useRef<(() => void) | null>(null);
  useEffect(() => {
    const unsubscribe = chatStore.onStreamEvent((event) => {
      if (event.kind === "streamEnd") listener.current?.(event.sessionId);
    });
    return () => {
      unsubscribe();
      listener.current = null;
      release.current?.();
    };
  }, []);
  const subscribeStreamEnd = useCallback(
    (next: StreamEndListener, cancelPending?: () => void) => {
      release.current?.();
      listener.current = next;
      release.current = cancelPending ?? null;
      // Keep the existing hook's queue dispatcher when its page leaves. It only
      // sends to the queued agent/thread and checks the current HITL snapshot.
      // A returning chat replaces it; the provider releases it on logout.
      return () => {};
    },
    [],
  );
  const value = useMemo(
    () => ({ queues, setQueues, subscribeStreamEnd }),
    [queues, subscribeStreamEnd],
  );
  return (
    <ChatMessageQueueContext.Provider value={value}>
      {children}
    </ChatMessageQueueContext.Provider>
  );
}
