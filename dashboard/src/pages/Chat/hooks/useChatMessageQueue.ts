import { useCallback, useEffect, useRef, useState } from "react";
import { generateId } from "../../../utils/messageParser";
import type { ChatAttachment, UserComposerContext } from "./sseHelpers";
import * as chatStore from "./chatStore";

export const CHAT_QUEUE_MAX_ITEMS = 10;

export type QueuedChatItem = {
  id: string;
  text: string;
  attachments?: ChatAttachment[];
  composerContext?: UserComposerContext;
  modelRef?: string | null;
  createdAt: number;
};

export type EnqueueChatItemInput = {
  text: string;
  attachments?: ChatAttachment[];
  composerContext?: UserComposerContext;
  modelRef?: string | null;
};

export type ChatQueueFlushContext = {
  agentId: string;
  threadId: string;
  queueKey: string;
};

/** Return `false` to re-queue the item at the head after a failed send. */
export type ChatQueueFlushHandler = (
  item: QueuedChatItem,
  ctx: ChatQueueFlushContext,
) => boolean | void;

export function threadQueueKey(
  agentId: string | null | undefined,
  threadId: string | null | undefined,
): string {
  return `${agentId ?? ""}:${threadId ?? ""}`;
}

export function parseThreadQueueKey(key: string): {
  agentId: string;
  threadId: string;
} {
  const idx = key.indexOf(":");
  if (idx < 0) return { agentId: key, threadId: "" };
  return { agentId: key.slice(0, idx), threadId: key.slice(idx + 1) };
}

function queueKeysForThread(
  queues: Record<string, QueuedChatItem[]>,
  threadId: string,
): string[] {
  if (!threadId) return [];
  const suffix = `:${threadId}`;
  return Object.keys(queues).filter(
    (k) => k.endsWith(suffix) && (queues[k]?.length ?? 0) > 0,
  );
}

function withoutQueueKey(
  prev: Record<string, QueuedChatItem[]>,
  key: string,
): Record<string, QueuedChatItem[]> {
  if (!(key in prev)) return prev;
  const { [key]: _, ...rest } = prev;
  return rest;
}

function defaultSubscribeStreamEnd(
  listener: (sessionId: string) => void,
): () => void {
  return chatStore.onStreamEvent((event) => {
    if (event.kind === "streamEnd") listener(event.sessionId);
  });
}

function defaultIsThreadStreaming(threadId: string): boolean {
  if (!threadId) return false;
  return chatStore.getSnapshot(threadId).isStreaming;
}

interface UseChatMessageQueueParams {
  agentId: string | null | undefined;
  threadId: string | null | undefined;
  isStreaming: boolean;
  onFlush: ChatQueueFlushHandler;
  /** Test seam — defaults to chatStore streamEnd events. */
  subscribeStreamEnd?: (listener: (sessionId: string) => void) => () => void;
  /** Test seam — defaults to chatStore session snapshot. */
  isThreadStreaming?: (threadId: string) => boolean;
}

/**
 * Per-thread FIFO message queue for typing while a turn is streaming.
 * Flushes when the active thread's `isStreaming` falls false, when a
 * chatStore `streamEnd` fires for a queued thread (incl. background), or
 * when returning to an idle thread that still has items.
 */
export function useChatMessageQueue({
  agentId,
  threadId,
  isStreaming,
  onFlush,
  subscribeStreamEnd = defaultSubscribeStreamEnd,
  isThreadStreaming = defaultIsThreadStreaming,
}: UseChatMessageQueueParams) {
  const [queues, setQueues] = useState<Record<string, QueuedChatItem[]>>({});
  const key = threadQueueKey(agentId, threadId);
  const items = queues[key] ?? [];

  const queuesRef = useRef(queues);
  queuesRef.current = queues;
  const onFlushRef = useRef(onFlush);
  onFlushRef.current = onFlush;
  const isThreadStreamingRef = useRef(isThreadStreaming);
  isThreadStreamingRef.current = isThreadStreaming;
  const flushTimerRef = useRef<number | null>(null);
  /** Streaming edge is tracked per queue key so thread switches never mis-flush. */
  const streamStateRef = useRef<{ key: string; streaming: boolean }>({
    key,
    streaming: isStreaming,
  });

  const writeQueues = useCallback((next: Record<string, QueuedChatItem[]>) => {
    queuesRef.current = next;
    setQueues(next);
  }, []);

  const enqueue = useCallback(
    (input: EnqueueChatItemInput): "ok" | "empty" | "full" => {
      const trimmed = input.text.trim();
      const hasAttachments = Boolean(input.attachments?.length);
      if (!trimmed && !hasAttachments) return "empty";

      const latest = queuesRef.current[key] ?? [];
      if (latest.length >= CHAT_QUEUE_MAX_ITEMS) return "full";

      const item: QueuedChatItem = {
        id: generateId(),
        text: trimmed,
        attachments:
          input.attachments && input.attachments.length > 0
            ? input.attachments.map((a) => ({ ...a }))
            : undefined,
        composerContext: input.composerContext
          ? { ...input.composerContext }
          : undefined,
        modelRef: input.modelRef ?? null,
        createdAt: Date.now(),
      };
      writeQueues({ ...queuesRef.current, [key]: [...latest, item] });
      return "ok";
    },
    [key, writeQueues],
  );

  const remove = useCallback(
    (id: string) => {
      const current = queuesRef.current[key] ?? [];
      const next = current.filter((item) => item.id !== id);
      if (next.length === current.length) return;
      if (next.length === 0) {
        writeQueues(withoutQueueKey(queuesRef.current, key));
        return;
      }
      writeQueues({ ...queuesRef.current, [key]: next });
    },
    [key, writeQueues],
  );

  const reclaim = useCallback(
    (id: string): QueuedChatItem | null => {
      const current = queuesRef.current[key] ?? [];
      const found = current.find((item) => item.id === id) ?? null;
      if (!found) return null;
      const next = current.filter((item) => item.id !== id);
      if (next.length === 0) {
        writeQueues(withoutQueueKey(queuesRef.current, key));
      } else {
        writeQueues({ ...queuesRef.current, [key]: next });
      }
      return found;
    },
    [key, writeQueues],
  );

  const clear = useCallback(() => {
    writeQueues(withoutQueueKey(queuesRef.current, key));
  }, [key, writeQueues]);

  /** Atomically pop head by id for the given queue key. */
  const dequeueHead = useCallback(
    (queueKey: string): QueuedChatItem | null => {
      const current = queuesRef.current[queueKey] ?? [];
      if (current.length === 0) return null;
      const head = current[0] ?? null;
      if (!head) return null;
      const next = current.filter((item) => item.id !== head.id);
      if (next.length === 0) {
        writeQueues(withoutQueueKey(queuesRef.current, queueKey));
      } else {
        writeQueues({ ...queuesRef.current, [queueKey]: next });
      }
      return head;
    },
    [writeQueues],
  );

  const requeueFront = useCallback(
    (queueKey: string, item: QueuedChatItem) => {
      const current = queuesRef.current[queueKey] ?? [];
      if (current.some((entry) => entry.id === item.id)) return;
      const next =
        current.length >= CHAT_QUEUE_MAX_ITEMS
          ? [item, ...current.slice(0, CHAT_QUEUE_MAX_ITEMS - 1)]
          : [item, ...current];
      writeQueues({ ...queuesRef.current, [queueKey]: next });
    },
    [writeQueues],
  );

  const cancelScheduledFlush = useCallback(() => {
    if (flushTimerRef.current != null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  }, []);

  const scheduleFlush = useCallback(
    (queueKey: string) => {
      cancelScheduledFlush();
      if ((queuesRef.current[queueKey] ?? []).length === 0) return;
      flushTimerRef.current = window.setTimeout(() => {
        flushTimerRef.current = null;
        const { agentId: flushAgentId, threadId: flushThreadId } =
          parseThreadQueueKey(queueKey);
        // Another turn may have started between schedule and fire.
        if (flushThreadId && isThreadStreamingRef.current(flushThreadId)) {
          return;
        }
        const head = dequeueHead(queueKey);
        if (!head) return;
        try {
          const ok = onFlushRef.current(head, {
            agentId: flushAgentId,
            threadId: flushThreadId,
            queueKey,
          });
          if (ok === false) {
            requeueFront(queueKey, head);
          }
        } catch {
          requeueFront(queueKey, head);
        }
      }, 0);
    },
    [cancelScheduledFlush, dequeueHead, requeueFront],
  );

  useEffect(() => {
    const prev = streamStateRef.current;
    streamStateRef.current = { key, streaming: isStreaming };

    if (prev.key !== key) {
      // Returning to an idle thread that still has a queue — resume sending.
      if (!isStreaming) {
        scheduleFlush(key);
      } else {
        cancelScheduledFlush();
      }
    } else if (prev.streaming && !isStreaming) {
      // Same thread: only flush on true → false.
      scheduleFlush(key);
    } else if (isStreaming) {
      // Stream resumed before the timer fired — keep the queue intact.
      cancelScheduledFlush();
    }

    return cancelScheduledFlush;
  }, [key, isStreaming, scheduleFlush, cancelScheduledFlush]);

  // Background (and active) threads: flush when chatStore reports streamEnd.
  useEffect(() => {
    return subscribeStreamEnd((sessionId) => {
      for (const queueKey of queueKeysForThread(queuesRef.current, sessionId)) {
        scheduleFlush(queueKey);
      }
    });
  }, [subscribeStreamEnd, scheduleFlush]);

  return {
    items,
    enqueue,
    remove,
    reclaim,
    clear,
  };
}
