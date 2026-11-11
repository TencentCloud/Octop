import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  octopThreadsApi,
  type OctopThreadHistory,
} from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { useChat } from "./useChat";
import {
  clearInflightTail,
  flushInflightTail,
  readInflightTail,
} from "../utils/inflightTranscriptCache";

const thread = "versioned-history-test";

afterEach(() => {
  vi.restoreAllMocks();
  chatStore.removeSession(thread);
  clearInflightTail(thread);
  chatStore.removeSession("other-history-thread");
});

function deferredHistory() {
  let resolve!: (history: OctopThreadHistory) => void;
  const promise = new Promise<OctopThreadHistory>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function flushHistoryRequest() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("history failures", () => {
  it("keeps a loaded conversation and its cursor when refreshing fails", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "old", role: "user", content: "keep me", timestamp: 1 }],
      { hasMore: true, nextOffset: 25, nextCursor: "boundary" },
    );
    vi.spyOn(octopThreadsApi, "history").mockRejectedValue(
      new Error("archive unavailable"),
    );
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.historyError).toBe(true);
    expect(chatStore.getSnapshot(thread).messages[0].content).toBe("keep me");
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe("boundary");
    expect(chatStore.getSnapshot(thread).historyHasMore).toBe(true);
  });

  it("does not mark a failed initial load as an empty hydrated conversation", async () => {
    const history = vi
      .spyOn(octopThreadsApi, "history")
      .mockRejectedValueOnce(new Error("decode failed"));
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.historyError).toBe(true);
    expect(chatStore.getSnapshot(thread).historyHydrated).toBe(false);
    history.mockResolvedValueOnce({
      thread_id: thread,
      messages: [{ id: "ok", role: "user", content: "restored" }],
      has_more: false,
    });
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.historyError).toBe(false);
    expect(chatStore.getSnapshot(thread).historyHydrated).toBe(true);
    expect(chatStore.getSnapshot(thread).messages[0].content).toBe("restored");
  });

  it("refetches a thread cached as empty so background turns show up", async () => {
    chatStore.setHistoryPage(thread, [], {
      hasMore: false,
      nextOffset: 0,
      nextCursor: null,
    });
    const history = vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: [{ id: "cron", role: "assistant", content: "task done" }],
      has_more: false,
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(history).toHaveBeenCalled();
    expect(chatStore.getSnapshot(thread).messages[0].content).toBe("task done");
  });

  it("passes the pinned cursor when loading older messages", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "new", role: "user", content: "new", timestamp: 1 }],
      { hasMore: true, nextOffset: 25, nextCursor: "pinned-boundary" },
    );
    const history = vi
      .spyOn(octopThreadsApi, "history")
      .mockResolvedValue({ thread_id: thread, messages: [], has_more: false });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadMoreHistory();
    });
    expect(history).toHaveBeenCalledWith(
      "agent",
      thread,
      expect.objectContaining({ cursor: "pinned-boundary" }),
    );
  });
  it("retries the failed older page with the same cursor", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "latest", role: "user", content: "latest", timestamp: 1 }],
      { hasMore: true, nextOffset: 25, nextCursor: "same-boundary" },
    );
    const history = vi
      .spyOn(octopThreadsApi, "history")
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce({
        thread_id: thread,
        messages: [{ id: "older", role: "user", content: "older" }],
        has_more: false,
      });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadMoreHistory();
    });
    expect(result.current.historyError).toBe(true);
    await act(async () => {
      await result.current.retryHistory();
    });
    expect(history).toHaveBeenLastCalledWith(
      "agent",
      thread,
      expect.objectContaining({ cursor: "same-boundary" }),
    );
    expect(result.current.historyError).toBe(false);
    expect(
      chatStore.getSnapshot(thread).messages.map((m) => m.content),
    ).toEqual(["older", "latest"]);
  });

  it("keeps a message sent while the history request is still in flight", async () => {
    let resolveHistory: (value: unknown) => void = () => {};
    const gate = new Promise((resolve) => {
      resolveHistory = resolve;
    });
    vi.spyOn(octopThreadsApi, "history").mockImplementation(
      () => gate as ReturnType<typeof octopThreadsApi.history>,
    );
    const { result } = renderHook(() => useChat(thread, "agent"));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.loadHistory(thread);
    });
    // Dynamic import inside the loader yields before the request is awaited.
    await flushHistoryRequest();
    act(() => {
      chatStore.appendUserMessage(thread, {
        id: "local-user",
        role: "user",
        content: "继续做",
        timestamp: Date.now(),
      });
    });
    resolveHistory({
      thread_id: thread,
      messages: [{ id: "old", role: "assistant", content: "之前的回复" }],
      has_more: false,
    });
    await act(async () => {
      await pending;
    });
    expect(
      chatStore.getSnapshot(thread).messages.map((message) => message.content),
    ).toEqual(["之前的回复", "继续做"]);
  });

  it("restores a cached in-flight reply that history has not stored yet", async () => {
    flushInflightTail(thread, [
      {
        id: "local-user",
        role: "user",
        content: "继续做",
        timestamp: 5_000,
      },
      {
        id: "local-a",
        role: "assistant",
        content: "已经写到这里了",
        status: "streaming",
        timestamp: 5_100,
      },
    ]);
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: [
        { id: "old", role: "assistant", content: "之前的回复" },
        { id: "local-user", role: "user", content: "继续做", timestamp: 5_000 },
      ],
      has_more: false,
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(
      chatStore.getSnapshot(thread).messages.map((message) => message.content),
    ).toEqual(["之前的回复", "继续做", "已经写到这里了"]);
  });

  it("refreshes a completed turn without replaying a longer local or cached bubble", async () => {
    const local = [
      { id: "u", role: "user" as const, content: "继续", timestamp: 20_000 },
      {
        id: "local-a",
        role: "assistant" as const,
        content: "旧的本地内容比最终回复长",
        status: "done" as const,
        timestamp: 20_100,
      },
    ];
    chatStore.setHistoryPage(thread, local, { hasMore: false, nextOffset: 0 });
    flushInflightTail(thread, local);
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: [
        { id: "u", role: "user", content: "继续", timestamp: 5_000 },
        { id: "srv-a", role: "assistant", content: "完成", timestamp: 5_100 },
      ],
      has_more: false,
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(
      chatStore.getSnapshot(thread).messages.map((message) => message.id),
    ).toEqual(["u", "srv-a"]);
    expect(chatStore.getSnapshot(thread).messages[0].timestamp).toBe(5_000);
    expect(readInflightTail(thread)).toBeNull();
  });
});

describe("cache ordering and stale history responses", () => {
  const latest: OctopThreadHistory = {
    thread_id: thread,
    messages: Array.from({ length: 25 }, (_, index) => ({
      id: `latest-${index}`,
      role: index % 2 ? "assistant" : "user",
      content: `15:02 message ${index}`,
      timestamp: 1000 + index,
    })),
    has_more: true,
    next_cursor: "latest-boundary",
  };
  const stale = [
    {
      id: "u11",
      role: "user" as const,
      content: "11:02 question",
      timestamp: 999999,
    },
    {
      id: "a11",
      role: "assistant" as const,
      content: "old reply",
      timestamp: 999999,
      status: "streaming" as const,
    },
  ];

  it("keeps an unmatched 11:02 cache out of the latest 25, then loads it once in its historical position", async () => {
    flushInflightTail(thread, stale);
    const history = vi
      .spyOn(octopThreadsApi, "history")
      .mockResolvedValueOnce(latest)
      .mockResolvedValueOnce(latest)
      .mockResolvedValueOnce({
        thread_id: thread,
        messages: stale,
        has_more: false,
      });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.messages.map((message) => message.id)).toEqual(
      latest.messages.map((message) => message.id),
    );
    expect(readInflightTail(thread)?.map((message) => message.id)).toEqual([
      "u11",
      "a11",
    ]);
    await act(async () => {
      await result.current.loadMoreHistory();
    });
    expect(history).toHaveBeenLastCalledWith(
      "agent",
      thread,
      expect.objectContaining({ cursor: "latest-boundary" }),
    );
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "u11",
      "a11",
      ...latest.messages.map((message) => message.id),
    ]);
    expect(
      new Set(result.current.messages.map((message) => message.id)).size,
    ).toBe(27);
  });

  it("does not treat a cached streaming flag as proof that a completed server reply is stale", async () => {
    flushInflightTail(thread, stale);
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      turn_active: false,
      messages: [stale[0], { id: "final", role: "assistant", content: "done" }],
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "u11",
      "final",
    ]);
    // An older server projection cannot justify deleting a longer cached copy.
    expect(readInflightTail(thread)?.[1].content).toBe("old reply");
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "u11",
      "final",
    ]);
  });

  it("restores a matching cached reply without importing an unmatched earlier cached turn", async () => {
    flushInflightTail(thread, [
      { ...stale[0], localPending: true },
      stale[1],
      {
        id: "current",
        role: "user",
        content: "current",
        timestamp: 1,
        localPending: true,
      },
      {
        id: "partial",
        role: "assistant",
        content: "partial",
        timestamp: 2,
        status: "streaming",
      },
    ]);
    expect(readInflightTail(thread)?.map((message) => message.id)).toEqual([
      "u11",
      "a11",
      "current",
      "partial",
    ]);
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      turn_active: true,
      messages: [{ id: "current", role: "user", content: "current" }],
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "current",
      "partial",
    ]);
  });

  it("resets a disconnected paging window when its only overlap is an optimistic send", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "old-window", role: "assistant", content: "old", timestamp: 1 }],
      { hasMore: false, nextOffset: 100, nextCursor: "gap" },
    );
    chatStore.appendUserMessage(thread, {
      id: "latest-0",
      role: "user",
      content: "new",
      timestamp: 2,
    });
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue(latest);
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.messages.map((message) => message.id)).toEqual(
      latest.messages.map((message) => message.id),
    );
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
      "latest-boundary",
    );
    expect(chatStore.getSnapshot(thread).historyHasMore).toBe(true);
  });

  it("ignores an older page that arrives after a latest-page refresh", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "initial", role: "user", content: "initial", timestamp: 1 }],
      { hasMore: true, nextOffset: 25, nextCursor: "old-boundary" },
    );
    const older = deferredHistory();
    vi.spyOn(octopThreadsApi, "history").mockImplementation(
      (_agent, _thread, options) =>
        options?.offset ? older.promise : Promise.resolve(latest),
    );
    const { result } = renderHook(() => useChat(thread, "agent"));
    let request!: Promise<boolean>;
    act(() => {
      request = result.current.loadMoreHistory();
    });
    await flushHistoryRequest();
    await act(async () => {
      await result.current.refreshHistory();
    });
    await act(async () => {
      older.resolve({ thread_id: thread, messages: stale, has_more: false });
      await request;
    });
    expect(result.current.messages.map((message) => message.id)).toEqual(
      latest.messages.map((message) => message.id),
    );
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
      "latest-boundary",
    );
    expect(chatStore.getSnapshot(thread).historyLoadingMore).toBe(false);
  });

  it.each(["clear", "remove", "navigate", "unmount"])(
    "ignores an initial history response after %s",
    async (action) => {
      const pending = deferredHistory();
      vi.spyOn(octopThreadsApi, "history").mockReturnValue(pending.promise);
      const { result, rerender, unmount } = renderHook(
        ({ id }) => useChat(id, "agent"),
        { initialProps: { id: thread } },
      );
      let request!: Promise<void>;
      act(() => {
        request = result.current.loadHistory(thread);
      });
      await flushHistoryRequest();
      act(() => {
        if (action === "clear") chatStore.clearMessages(thread);
        else if (action === "remove") chatStore.removeSession(thread);
        else if (action === "navigate")
          rerender({ id: "other-history-thread" });
        else unmount();
      });
      await act(async () => {
        pending.resolve(latest);
        await request;
      });
      expect(chatStore.getSnapshot(thread).messages).toEqual([]);
      expect(chatStore.getSnapshot(thread).historyHydrated).toBe(false);
    },
  );

  it("keeps an edited send when a history response fetched before the edit arrives", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "original", role: "user", content: "before", timestamp: 1 }],
      { hasMore: false, nextOffset: 0 },
    );
    const pending = deferredHistory();
    vi.spyOn(octopThreadsApi, "history").mockReturnValue(pending.promise);
    const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
    const { result } = renderHook(() => useChat(thread, "agent"));
    let request!: Promise<void>;
    act(() => {
      request = result.current.refreshHistory();
    });
    await flushHistoryRequest();
    act(() => {
      result.current.editAndResend("original", "after", "", "agent");
    });
    const edited = chatStore.getSnapshot(thread).messages[0];
    expect(edited.id).not.toBe("original");
    expect(edited.localPending).toBe(true);
    expect(send.mock.calls[0][15]).toBe(edited.id);
    await act(async () => {
      pending.resolve(latest);
      await request;
    });
    expect(result.current.messages.map((message) => message.content)).toEqual([
      "after",
    ]);
  });

  it("rejects a history response belonging to a different thread", async () => {
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      ...latest,
      thread_id: "other-history-thread",
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.messages).toEqual([]);
    expect(result.current.historyError).toBe(true);
  });

  it("does not let a previous thread's finally block clear the current refresh state", async () => {
    const first = deferredHistory();
    const second = deferredHistory();
    vi.spyOn(octopThreadsApi, "history").mockImplementation((_agent, id) =>
      id === thread ? first.promise : second.promise,
    );
    const { result, rerender } = renderHook(({ id }) => useChat(id, "agent"), {
      initialProps: { id: thread },
    });
    let oldRequest!: Promise<void>;
    act(() => {
      oldRequest = result.current.refreshHistory();
    });
    await flushHistoryRequest();
    rerender({ id: "other-history-thread" });
    let newRequest!: Promise<void>;
    act(() => {
      newRequest = result.current.refreshHistory();
    });
    await flushHistoryRequest();
    await act(async () => {
      first.resolve(latest);
      await oldRequest;
    });
    expect(result.current.historyRefreshing).toBe(true);
    expect(result.current.messages).toEqual([]);
    await act(async () => {
      second.resolve({ ...latest, thread_id: "other-history-thread" });
      await newRequest;
    });
    expect(result.current.historyRefreshing).toBe(false);
    expect(result.current.messages).toHaveLength(25);
  });
});
