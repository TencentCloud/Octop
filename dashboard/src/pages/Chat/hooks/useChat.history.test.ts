import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { useChat, type ChatMessage } from "./useChat";

const thread = "versioned-history-test";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  chatStore.removeSession(thread);
});

describe("bottom-scroll history refresh", () => {
  const user: ChatMessage = {
    id: "question",
    role: "user",
    content: "question",
    timestamp: 1,
  };
  const thinking: ChatMessage = {
    id: "thinking",
    role: "assistant",
    content: "",
    contentBlocks: [{ type: "thinking", content: "visible reasoning" }],
    timestamp: 2,
  };
  const readyPage = {
    thread_id: thread,
    messages: [
      user,
      {
        id: "thinking",
        role: "assistant",
        content: [
          { type: "thinking", thinking: "visible reasoning" },
          { type: "text", text: "finished answer" },
        ],
      },
    ],
    has_more: false,
  };

  beforeEach(() => {
    vi.spyOn(chatStore, "attachThread").mockResolvedValue();
    chatStore.setHistoryPage(thread, [user, thinking], {
      hasMore: true,
      nextOffset: 50,
      nextCursor: "older-boundary",
    });
  });

  it("keeps thinking visible until the history projection is ready", async () => {
    vi.useFakeTimers();
    const history = vi
      .spyOn(octopThreadsApi, "history")
      .mockResolvedValueOnce({
        thread_id: thread,
        messages: [],
        has_more: false,
        history_loading: true,
        history_retry_after_ms: 1500,
      })
      .mockResolvedValueOnce(readyPage);
    const { result } = renderHook(() => useChat(thread, "agent"));
    let refresh!: Promise<void>;
    await act(async () => {
      refresh = result.current.refreshHistory();
      await vi.waitFor(() => expect(history).toHaveBeenCalledTimes(1));
    });
    expect(history).toHaveBeenCalledTimes(1);
    expect(result.current.messages).toEqual([user, thinking]);
    expect(result.current.historyRefreshing).toBe(true);
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
      "older-boundary",
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
      await refresh;
    });
    expect(history).toHaveBeenCalledTimes(2);
    expect(result.current.messages.at(-1)?.content).toBe("finished answer");
    expect(result.current.messages.at(-1)?.contentBlocks).toContainEqual(
      thinking.contentBlocks![0],
    );
    expect(result.current.historyRefreshing).toBe(false);
  });

  it("keeps thinking and the cursor if the projection retry fails", async () => {
    vi.useFakeTimers();
    vi.spyOn(octopThreadsApi, "history")
      .mockResolvedValueOnce({
        thread_id: thread,
        messages: [],
        has_more: false,
        history_loading: true,
        history_retry_after_ms: 500,
      })
      .mockRejectedValueOnce(new Error("history unavailable"));
    const { result } = renderHook(() => useChat(thread, "agent"));
    let refresh!: Promise<void>;
    await act(async () => {
      refresh = result.current.refreshHistory();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
      await refresh;
    });
    expect(result.current.messages).toEqual([user, thinking]);
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
      "older-boundary",
    );
    expect(result.current.historyError).toBe(true);
    expect(result.current.historyRefreshing).toBe(false);
  });

  it.each([
    { messages: [], history_loading: false },
    { messages: [user], history_loading: false },
    { messages: [], history_loading: true },
  ])(
    "preserves the live tail and reattaches when server history is incomplete: $messages",
    async ({ messages, history_loading }) => {
      vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
        thread_id: thread,
        messages,
        has_more: false,
        turn_active: true,
        history_loading,
      });
      const { result } = renderHook(() => useChat(thread, "agent"));
      await act(async () => {
        await result.current.refreshHistory();
      });
      expect(result.current.messages).toEqual([user, thinking]);
      expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
        "older-boundary",
      );
      expect(chatStore.attachThread).toHaveBeenCalledWith(
        thread,
        "agent",
        thread,
      );
      expect(result.current.historyRefreshing).toBe(false);
    },
  );

  it.each(["append", "prepend", "clear", "reasoning"])(
    "does not overwrite a concurrent %s with an older HTTP response",
    async (change) => {
      let resolve!: (page: typeof readyPage) => void;
      vi.spyOn(octopThreadsApi, "history").mockImplementation(
        () =>
          new Promise((r) => {
            resolve = r;
          }),
      );
      const { result } = renderHook(() => useChat(thread, "agent"));
      let refresh!: Promise<void>;
      await act(async () => {
        refresh = result.current.refreshHistory();
      });
      act(() => {
        if (change === "append") {
          chatStore.appendUserMessage(thread, { ...user, id: "new-question" });
        } else if (change === "prepend") {
          chatStore.prependHistoryMessages(
            thread,
            [{ ...user, id: "older-question" }],
            { hasMore: true, nextOffset: 75, nextCursor: "new-boundary" },
          );
        } else if (change === "reasoning") {
          chatStore.setMessages(thread, [
            user,
            {
              ...thinking,
              contentBlocks: [
                { type: "thinking", content: "newer streamed reasoning" },
              ],
            },
          ]);
        } else {
          chatStore.clearMessages(thread);
        }
      });
      const current = chatStore.getSnapshot(thread);
      await act(async () => {
        resolve(readyPage);
        await refresh;
      });
      expect(result.current.messages).toEqual(current.messages);
      expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
        current.historyNextCursor,
      );
      expect(result.current.historyRefreshing).toBe(false);
    },
  );

  it.each(["unmount", "switch"])(
    "stops projection retries after %s",
    async (change) => {
      vi.useFakeTimers();
      const history = vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
        thread_id: thread,
        messages: [],
        has_more: false,
        history_loading: true,
        history_retry_after_ms: 500,
      });
      const { result, unmount, rerender } = renderHook(
        ({ id }) => useChat(id, "agent"),
        { initialProps: { id: thread } },
      );
      let refresh!: Promise<void>;
      await act(async () => {
        refresh = result.current.refreshHistory();
        await vi.waitFor(() => expect(history).toHaveBeenCalledOnce());
      });
      if (change === "unmount") unmount();
      else rerender({ id: "other-thread" });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
        await refresh;
      });
      expect(history).toHaveBeenCalledOnce();
      expect(chatStore.getSnapshot(thread).messages).toEqual([user, thinking]);
      chatStore.removeSession("other-thread");
    },
  );

  it("still refreshes completed history and preserves previously loaded older pages", async () => {
    const older = { ...user, id: "older-question" };
    chatStore.prependHistoryMessages(thread, [older], {
      hasMore: true,
      nextOffset: 75,
      nextCursor: "oldest-boundary",
    });
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue(readyPage);
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.messages[0]).toEqual(older);
    expect(result.current.messages.at(-1)?.content).toBe("finished answer");
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe(
      "oldest-boundary",
    );
    expect(chatStore.getSnapshot(thread).historyNextOffset).toBe(75);
  });

  it("accepts an authoritative empty history after a completed turn", async () => {
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: [],
      has_more: false,
      turn_active: false,
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.messages).toEqual([]);
  });
});

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
});
