import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHAT_QUEUE_MAX_ITEMS,
  useChatMessageQueue,
} from "./useChatMessageQueue";

describe("useChatMessageQueue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const idleStreaming = () => false;

  it("enqueues FIFO and enforces the max size", () => {
    const onFlush = vi.fn();
    const { result } = renderHook(() =>
      useChatMessageQueue({
        agentId: "agent-1",
        threadId: "thread-1",
        isStreaming: true,
        onFlush,
        subscribeStreamEnd: () => () => undefined,
        isThreadStreaming: idleStreaming,
      }),
    );

    act(() => {
      for (let i = 0; i < CHAT_QUEUE_MAX_ITEMS; i++) {
        expect(result.current.enqueue({ text: `msg-${i}` })).toBe("ok");
      }
    });
    expect(result.current.items).toHaveLength(CHAT_QUEUE_MAX_ITEMS);
    let overflow: "ok" | "empty" | "full" = "ok";
    act(() => {
      overflow = result.current.enqueue({ text: "overflow" });
    });
    expect(overflow).toBe("full");
    expect(result.current.items[0]?.text).toBe("msg-0");
    expect(result.current.items.at(-1)?.text).toBe(
      `msg-${CHAT_QUEUE_MAX_ITEMS - 1}`,
    );
    expect(onFlush).not.toHaveBeenCalled();
  });

  it("isolates queues per thread", () => {
    const onFlush = vi.fn();
    const { result, rerender } = renderHook(
      ({ threadId }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId,
          isStreaming: true,
          onFlush,
          subscribeStreamEnd: () => () => undefined,
          isThreadStreaming: idleStreaming,
        }),
      { initialProps: { threadId: "t1" } },
    );

    act(() => {
      expect(result.current.enqueue({ text: "one" })).toBe("ok");
    });
    expect(result.current.items).toHaveLength(1);

    rerender({ threadId: "t2" });
    expect(result.current.items).toHaveLength(0);
    act(() => {
      expect(result.current.enqueue({ text: "two" })).toBe("ok");
    });
    expect(result.current.items[0]?.text).toBe("two");

    rerender({ threadId: "t1" });
    expect(result.current.items[0]?.text).toBe("one");
  });

  it("flushes the head item when streaming ends", () => {
    const onFlush = vi.fn();
    const { result, rerender } = renderHook(
      ({ isStreaming }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId: "thread-1",
          isStreaming,
          onFlush,
          subscribeStreamEnd: () => () => undefined,
          isThreadStreaming: idleStreaming,
        }),
      { initialProps: { isStreaming: true } },
    );

    act(() => {
      result.current.enqueue({ text: "first" });
      result.current.enqueue({ text: "second" });
    });
    expect(result.current.items).toHaveLength(2);

    rerender({ isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });

    expect(onFlush).toHaveBeenCalledTimes(1);
    expect(onFlush.mock.calls[0]?.[0]?.text).toBe("first");
    expect(onFlush.mock.calls[0]?.[1]).toMatchObject({
      agentId: "agent-1",
      threadId: "thread-1",
    });
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]?.text).toBe("second");
  });

  it("does not flush another thread when switching away mid-stream", () => {
    const onFlush = vi.fn();
    const { result, rerender } = renderHook(
      ({ threadId, isStreaming }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId,
          isStreaming,
          onFlush,
          subscribeStreamEnd: () => () => undefined,
          isThreadStreaming: idleStreaming,
        }),
      { initialProps: { threadId: "t1", isStreaming: true } },
    );

    act(() => {
      result.current.enqueue({ text: "queued-on-t1" });
    });

    // Switch to idle t2 — must not flush t1's queue as a side effect.
    rerender({ threadId: "t2", isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).not.toHaveBeenCalled();

    // Returning to idle t1 resumes the pending queue (stream already ended).
    rerender({ threadId: "t1", isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).toHaveBeenCalledTimes(1);
    expect(onFlush.mock.calls[0]?.[0]?.text).toBe("queued-on-t1");
    expect(result.current.items).toHaveLength(0);
  });

  it("flushes a background thread on streamEnd while viewing another", () => {
    const onFlush = vi.fn();
    let emitEnd: ((sessionId: string) => void) | null = null;

    const { result, rerender } = renderHook(
      ({ threadId, isStreaming }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId,
          isStreaming,
          onFlush,
          subscribeStreamEnd: (listener) => {
            emitEnd = listener;
            return () => {
              emitEnd = null;
            };
          },
          isThreadStreaming: idleStreaming,
        }),
      { initialProps: { threadId: "t1", isStreaming: true } },
    );

    act(() => {
      result.current.enqueue({ text: "bg-msg" });
    });

    // Switch away; t1 still has a queue, active view is idle t2.
    rerender({ threadId: "t2", isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).not.toHaveBeenCalled();

    act(() => {
      emitEnd?.("t1");
      vi.runAllTimers();
    });

    expect(onFlush).toHaveBeenCalledTimes(1);
    expect(onFlush.mock.calls[0]?.[0]?.text).toBe("bg-msg");
    expect(onFlush.mock.calls[0]?.[1]?.threadId).toBe("t1");
  });

  it("requeues the head when onFlush returns false", () => {
    const onFlush = vi.fn(() => false);
    const { result, rerender } = renderHook(
      ({ isStreaming }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId: "thread-1",
          isStreaming,
          onFlush,
          subscribeStreamEnd: () => () => undefined,
          isThreadStreaming: idleStreaming,
        }),
      { initialProps: { isStreaming: true } },
    );

    act(() => {
      result.current.enqueue({ text: "retry-me" });
      result.current.enqueue({ text: "second" });
    });

    rerender({ isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });

    expect(onFlush).toHaveBeenCalledTimes(1);
    expect(result.current.items).toHaveLength(2);
    expect(result.current.items[0]?.text).toBe("retry-me");
    expect(result.current.items[1]?.text).toBe("second");
  });

  it("skips dequeue while the target thread is still streaming", () => {
    const onFlush = vi.fn();
    const streamingById = new Map<string, boolean>([["thread-1", true]]);
    const { result, rerender } = renderHook(
      ({ isStreaming }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId: "thread-1",
          isStreaming,
          onFlush,
          subscribeStreamEnd: () => () => undefined,
          isThreadStreaming: (id) => streamingById.get(id) ?? false,
        }),
      { initialProps: { isStreaming: true } },
    );

    act(() => {
      result.current.enqueue({ text: "wait" });
    });

    rerender({ isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).not.toHaveBeenCalled();
    expect(result.current.items).toHaveLength(1);

    streamingById.set("thread-1", false);
    rerender({ isStreaming: true });
    rerender({ isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).toHaveBeenCalledTimes(1);
    expect(onFlush.mock.calls[0]?.[0]?.text).toBe("wait");
  });

  it("allows a later flush after a cancelled schedule", () => {
    const onFlush = vi.fn();
    const { result, rerender } = renderHook(
      ({ isStreaming }) =>
        useChatMessageQueue({
          agentId: "agent-1",
          threadId: "thread-1",
          isStreaming,
          onFlush,
          subscribeStreamEnd: () => () => undefined,
          isThreadStreaming: idleStreaming,
        }),
      { initialProps: { isStreaming: true } },
    );

    act(() => {
      result.current.enqueue({ text: "keep" });
    });

    rerender({ isStreaming: false });
    rerender({ isStreaming: true });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).not.toHaveBeenCalled();

    rerender({ isStreaming: false });
    act(() => {
      vi.runAllTimers();
    });
    expect(onFlush).toHaveBeenCalledTimes(1);
    expect(onFlush.mock.calls[0]?.[0]?.text).toBe("keep");
  });

  it("reclaims by id without dropping the head", () => {
    const onFlush = vi.fn();
    const { result } = renderHook(() =>
      useChatMessageQueue({
        agentId: "agent-1",
        threadId: "thread-1",
        isStreaming: true,
        onFlush,
        subscribeStreamEnd: () => () => undefined,
        isThreadStreaming: idleStreaming,
      }),
    );

    act(() => {
      result.current.enqueue({ text: "keep" });
      result.current.enqueue({ text: "edit-me" });
    });
    const id = result.current.items[1]?.id;
    expect(id).toBeTruthy();

    let reclaimed = null as ReturnType<typeof result.current.reclaim>;
    act(() => {
      reclaimed = result.current.reclaim(id!);
    });
    expect(reclaimed?.text).toBe("edit-me");
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]?.text).toBe("keep");
  });
});
