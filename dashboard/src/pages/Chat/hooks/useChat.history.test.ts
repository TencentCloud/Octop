import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { useChat } from "./useChat";
import {
  clearInflightTail,
  flushInflightTail,
  readInflightTail,
  readRecoveryMessages,
  saveRecoveryMessages,
} from "../utils/inflightTranscriptCache";

const thread = "versioned-history-test";

beforeEach(() => {
  vi.spyOn(octopThreadsApi, "reconcile").mockResolvedValue({
    thread_id: thread,
    receipts: {},
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  chatStore.removeSession(thread);
  clearInflightTail(thread);
  saveRecoveryMessages(thread, []);
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
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
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
        {
          id: "u",
          role: "user",
          content: "继续",
          timestamp: 5_000,
          turn_status: "complete",
        },
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

describe("pagination and recovery consistency", () => {
  const stale: import("./sseHelpers").ChatMessage[] = [
    { id: "u11", role: "user", content: "11:02", timestamp: 11_000 },
    {
      id: "a11",
      role: "assistant",
      content: "old reply",
      timestamp: 11_100,
      status: "done",
    },
  ];
  const latest = [
    {
      id: "u15",
      role: "user",
      content: "15:01",
      timestamp: 15_000,
      server_order: [2, 50] as [number, number],
    },
    {
      id: "a15",
      role: "assistant",
      content: "15:02",
      timestamp: 15_100,
      server_order: [2, 51] as [number, number],
    },
  ];

  it("does not replay a confirmed old cache outside the latest page", async () => {
    flushInflightTail(thread, stale);
    vi.mocked(octopThreadsApi.reconcile).mockResolvedValue({
      thread_id: thread,
      receipts: {
        u11: { state: "stored", persisted: true, server_order: [2, 1] },
      },
    });
    const history = vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: latest,
      has_more: true,
      next_cursor: "older",
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(chatStore.getSnapshot(thread).messages.map((m) => m.id)).toEqual([
      "u15",
      "a15",
    ]);
    expect(readInflightTail(thread)).toBeNull();
    history.mockResolvedValueOnce({
      thread_id: thread,
      messages: stale.map((m, i) => ({
        ...m,
        server_order: [2, i + 1] as [number, number],
      })),
      has_more: false,
    });
    await act(async () => {
      await result.current.loadMoreHistory();
    });
    expect(chatStore.getSnapshot(thread).messages.map((m) => m.id)).toEqual([
      "u11",
      "a11",
      "u15",
      "a15",
    ]);
  });

  it("retains unknown recovery separately, including after a new local send", async () => {
    flushInflightTail(thread, stale);
    vi.mocked(octopThreadsApi.reconcile).mockRejectedValue(
      new Error("offline"),
    );
    vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: latest,
      has_more: true,
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(result.current.messages.map((m) => m.id)).toEqual(["u15", "a15"]);
    expect(result.current.recoveryMessages.map((m) => m.id)).toEqual([
      "u11",
      "a11",
    ]);
    act(() => {
      chatStore.appendUserMessage(thread, {
        id: "new",
        role: "user",
        content: "new message",
        timestamp: 1,
      });
    });
    expect(readRecoveryMessages(thread).map((m) => m.id)).toEqual([
      "u11",
      "a11",
    ]);
  });

  it("queries persistence before loading the page so a late completion cannot discard the final reply", async () => {
    flushInflightTail(thread, [
      {
        id: "u",
        role: "user",
        content: "question",
        timestamp: 1,
        delivery: "accepted",
      },
      {
        id: "local-a",
        role: "assistant",
        content: "final",
        timestamp: 2,
        status: "done",
      },
    ]);
    const calls: string[] = [];
    vi.mocked(octopThreadsApi.reconcile).mockImplementation(async () => {
      calls.push("receipt");
      return {
        thread_id: thread,
        receipts: { u: { state: "stored", persisted: true } },
      };
    });
    vi.spyOn(octopThreadsApi, "history").mockImplementation(async () => {
      calls.push("history");
      return {
        thread_id: thread,
        messages: [
          {
            id: "u",
            role: "user",
            content: "question",
            turn_status: "complete",
          },
          { id: "server-a", role: "assistant", content: "final" },
        ],
      };
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.loadHistory(thread);
    });
    expect(calls).toEqual(["receipt", "history"]);
    expect(result.current.messages.map((m) => m.id)).toEqual(["u", "server-a"]);
    expect(readInflightTail(thread)).toBeNull();
  });

  it("keeps a locally completed reply until the server confirms persistence", async () => {
    const local = [
      {
        id: "u",
        role: "user" as const,
        content: "question",
        timestamp: 1,
        delivery: "accepted" as const,
      },
      {
        id: "local-a",
        role: "assistant" as const,
        content: "final local reply",
        timestamp: 2,
        status: "done" as const,
      },
    ];
    chatStore.setHistoryPage(thread, local, { hasMore: false, nextOffset: 0 });
    flushInflightTail(thread, local);
    vi.mocked(octopThreadsApi.reconcile).mockResolvedValue({
      thread_id: thread,
      receipts: {
        u: { state: "stored", persisted: false, turn_status: "active" },
      },
    });
    const history = vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
      thread_id: thread,
      messages: [{ id: "u", role: "user", content: "question" }],
    });
    const { result } = renderHook(() => useChat(thread, "agent"));
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.messages.at(-1)?.content).toBe("final local reply");
    expect(readInflightTail(thread)).not.toBeNull();
    vi.mocked(octopThreadsApi.reconcile).mockResolvedValue({
      thread_id: thread,
      receipts: { u: { state: "stored", persisted: true } },
    });
    history.mockResolvedValue({
      thread_id: thread,
      messages: [
        { id: "u", role: "user", content: "question", turn_status: "complete" },
        { id: "server-a", role: "assistant", content: "short final" },
      ],
    });
    await act(async () => {
      await result.current.refreshHistory();
    });
    expect(result.current.messages.map((m) => m.id)).toEqual(["u", "server-a"]);
    expect(readInflightTail(thread)).toBeNull();
  });

  it("ignores an older-page response that arrives after a newer refresh", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "initial", role: "user", content: "initial", timestamp: 1 }],
      { hasMore: true, nextOffset: 25, nextCursor: "old-cursor" },
    );
    let resolveOlder!: (
      value: import("../../../api/modules/octopThreads").OctopThreadHistory,
    ) => void;
    const older = new Promise<
      import("../../../api/modules/octopThreads").OctopThreadHistory
    >((resolve) => {
      resolveOlder = resolve;
    });
    vi.spyOn(octopThreadsApi, "history").mockImplementation(
      (_agent, _thread, params) =>
        params?.cursor
          ? older
          : Promise.resolve({
              thread_id: thread,
              messages: latest,
              has_more: true,
              next_cursor: "new-cursor",
            }),
    );
    const { result } = renderHook(() => useChat(thread, "agent"));
    let pending!: Promise<boolean>;
    act(() => {
      pending = result.current.loadMoreHistory();
    });
    await act(async () => {
      await result.current.refreshHistory();
    });
    await act(async () => {
      resolveOlder({ thread_id: thread, messages: stale, has_more: false });
      await pending;
    });
    expect(result.current.messages.map((m) => m.id)).toEqual(["u15", "a15"]);
    expect(chatStore.getSnapshot(thread).historyNextCursor).toBe("new-cursor");
  });

  it("ignores history arriving after the conversation was cleared", async () => {
    chatStore.setHistoryPage(
      thread,
      [{ id: "initial", role: "user", content: "initial", timestamp: 1 }],
      { hasMore: false, nextOffset: 0 },
    );
    let resolveHistory!: (
      value: import("../../../api/modules/octopThreads").OctopThreadHistory,
    ) => void;
    vi.spyOn(octopThreadsApi, "history").mockReturnValue(
      new Promise((resolve) => {
        resolveHistory = resolve;
      }),
    );
    const { result } = renderHook(() => useChat(thread, "agent"));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.refreshHistory();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    act(() => {
      chatStore.clearMessages(thread);
    });
    await act(async () => {
      resolveHistory({ thread_id: thread, messages: latest });
      await pending;
    });
    expect(result.current.messages).toEqual([]);
  });

  it("gives an edited send a new identity and ignores history fetched before the edit", async () => {
    chatStore.setHistoryPage(
      thread,
      [
        {
          id: "original",
          role: "user",
          content: "before",
          timestamp: 1,
          serverOrder: [0, 1],
          turnStatus: "complete",
        },
      ],
      { hasMore: false, nextOffset: 0 },
    );
    let resolveHistory!: (
      value: import("../../../api/modules/octopThreads").OctopThreadHistory,
    ) => void;
    vi.spyOn(octopThreadsApi, "history").mockReturnValue(
      new Promise((resolve) => {
        resolveHistory = resolve;
      }),
    );
    const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
    const { result } = renderHook(() => useChat(thread, "agent"));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.refreshHistory();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    act(() => {
      result.current.editAndResend("original", "after", "", "agent");
    });
    const edited = chatStore.getSnapshot(thread).messages[0];
    expect(edited.id).not.toBe("original");
    expect(edited.delivery).toBe("pending");
    expect(edited.serverOrder).toBeUndefined();
    expect(send.mock.calls[0][15]).toBe(edited.id);
    await act(async () => {
      resolveHistory({ thread_id: thread, messages: latest });
      await pending;
    });
    expect(result.current.messages.map((m) => m.content)).toEqual(["after"]);
  });
});

it("restores only the server-identified active turn while legacy history is being projected", async () => {
  flushInflightTail(thread, [
    { id: "active-user", role: "user", content: "still running", timestamp: 1 },
    {
      id: "partial",
      role: "assistant",
      content: "already received",
      timestamp: 2,
      status: "streaming",
    },
  ]);
  vi.mocked(octopThreadsApi.reconcile).mockResolvedValue({
    thread_id: thread,
    receipts: {
      "active-user": {
        state: "active",
        persisted: false,
        turn_status: "active",
      },
    },
  });
  vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
    thread_id: thread,
    messages: [],
    history_loading: true,
    turn_active: true,
    active_user_message_id: "active-user",
  });
  const { result } = renderHook(() => useChat(thread, "agent"));
  await act(async () => {
    await result.current.loadHistory(thread);
  });
  expect(result.current.messages.map((m) => m.id)).toEqual([
    "active-user",
    "partial",
  ]);
  expect(result.current.messages[1].content).toBe("already received");
  expect(result.current.historyLoading).toBe(false);
  expect(readInflightTail(thread)).not.toBeNull();
});

it("does not replay an active receipt after the history snapshot has advanced to another turn", async () => {
  flushInflightTail(thread, [
    { id: "old-active", role: "user", content: "11:02", timestamp: 1 },
    {
      id: "old-partial",
      role: "assistant",
      content: "old reply",
      timestamp: 2,
      status: "streaming",
    },
  ]);
  vi.mocked(octopThreadsApi.reconcile).mockResolvedValue({
    thread_id: thread,
    receipts: { "old-active": { state: "active", persisted: false } },
  });
  vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
    thread_id: thread,
    messages: [
      { id: "new-user", role: "user", content: "15:01", server_order: [3, 50] },
      {
        id: "new-answer",
        role: "assistant",
        content: "15:02",
        server_order: [3, 51],
      },
    ],
    turn_active: true,
    active_user_message_id: "new-user",
  });
  const { result } = renderHook(() => useChat(thread, "agent"));
  await act(async () => {
    await result.current.loadHistory(thread);
  });
  expect(result.current.messages.map((m) => m.id)).toEqual([
    "new-user",
    "new-answer",
  ]);
  expect(result.current.recoveryMessages.map((m) => m.id)).toEqual([
    "old-active",
    "old-partial",
  ]);
});

it("keeps the server paging cursor when an unconfirmed local prefix cannot establish full coverage", async () => {
  chatStore.setHistoryPage(
    thread,
    [
      {
        id: "old-u",
        role: "user",
        content: "old",
        timestamp: 1,
        serverOrder: [2, 1],
        delivery: "accepted",
      },
      {
        id: "old-live",
        role: "assistant",
        content: "long old reply",
        timestamp: 2,
      },
      {
        id: "new-u",
        role: "user",
        content: "new",
        timestamp: 3,
        delivery: "pending",
      },
    ],
    { hasMore: false, nextOffset: 0, nextCursor: null },
  );
  vi.mocked(octopThreadsApi.reconcile).mockResolvedValue({
    thread_id: thread,
    receipts: {
      "old-u": { state: "stored", persisted: true },
      "new-u": { state: "stored", persisted: true },
    },
  });
  vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
    thread_id: thread,
    messages: [
      {
        id: "old-final",
        role: "assistant",
        content: "old final",
        server_order: [2, 49],
      },
      { id: "new-u", role: "user", content: "new", server_order: [2, 50] },
      {
        id: "new-final",
        role: "assistant",
        content: "new final",
        server_order: [2, 51],
      },
    ],
    has_more: true,
    next_cursor: "before-49",
  });
  const { result } = renderHook(() => useChat(thread, "agent"));
  await act(async () => {
    await result.current.refreshHistory();
  });
  expect(result.current.messages.map((m) => m.id)).toEqual([
    "old-final",
    "new-u",
    "new-final",
  ]);
  expect(result.current.historyHasMore).toBe(true);
  expect(chatStore.getSnapshot(thread).historyNextCursor).toBe("before-49");
});
