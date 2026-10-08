import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { useChat } from "./useChat";
import type { ChatMessage } from "./sseHelpers";

const source = "edit-source";
const dest = "edit-destination";
const messages: ChatMessage[] = [
  { id: "ui-user-1", role: "user", content: "first", timestamp: 1 },
  { id: "ui-answer-1", role: "assistant", content: "answer", timestamp: 2 },
  {
    id: "ui-user-2",
    role: "user",
    content: "old",
    timestamp: 3,
    attachments: [
      { url: "/image.png", kind: "image", workspacePath: "inbound/image.png" },
    ],
    composerContext: {
      model: "openai/model",
      connectors: ["web"],
      knowledgeBaseIds: ["kb"],
      targetAgents: ["expert"],
      reasoningMode: "enabled",
      reasoningEffort: "high",
    },
  },
  { id: "ui-answer-2", role: "assistant", content: "old answer", timestamp: 4 },
  { id: "ui-user-3", role: "user", content: "later", timestamp: 5 },
];

function seed() {
  chatStore.setHistoryPage(source, messages, {
    hasMore: true,
    nextOffset: 25,
    nextCursor: "old-cursor",
  });
}
afterEach(() => {
  vi.restoreAllMocks();
  chatStore.removeSession(source);
  chatStore.removeSession(dest);
});

it("forks before the selected user, hydrates server history and resends attachments/settings only in the new thread", async () => {
  seed();
  const fork = vi.spyOn(octopThreadsApi, "fork").mockResolvedValue({
    thread_id: dest,
    session_key: "sk",
    source_thread_id: source,
    copied_messages: 2,
    title: null,
    last_active: 0,
    created_at: 0,
  });
  vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
    thread_id: dest,
    messages: [
      { id: "real-user", role: "user", content: "first" },
      { id: "real-answer", role: "assistant", content: "answer" },
    ],
    has_more: false,
  });
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  let created;
  await act(async () => {
    created = await result.current.editAndResend(
      "ui-user-2",
      "replacement",
      "",
      "agent",
    );
  });
  expect(fork).toHaveBeenCalledWith("agent", source, {
    message_id: "ui-user-2",
    content: "old",
    user_turns_from_end: 2,
  });
  expect(created).toMatchObject({ thread_id: dest });
  expect(chatStore.getSnapshot(source).messages).toEqual(messages);
  expect(chatStore.getSnapshot(dest).messages.map((m) => m.content)).toEqual([
    "first",
    "answer",
    "replacement",
  ]);
  expect(send).toHaveBeenCalledWith(
    dest,
    "replacement",
    "agent",
    "",
    messages[2].attachments,
    undefined,
    "openai/model",
    dest,
    ["web"],
    ["kb"],
    ["expert"],
    "enabled",
    "high",
    undefined,
    undefined,
  );
});

it("preserves history and cursor and sends nothing when the fork fails", async () => {
  seed();
  vi.spyOn(octopThreadsApi, "fork").mockRejectedValue(new Error("copy failed"));
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  await act(async () => {
    await expect(
      result.current.editAndResend("ui-user-1", "replacement", "", "agent"),
    ).rejects.toThrow("copy failed");
  });
  expect(chatStore.getSnapshot(source).messages).toEqual(messages);
  expect(chatStore.getSnapshot(source).historyNextCursor).toBe("old-cursor");
  expect(send).not.toHaveBeenCalled();
});

it("does not fork or cancel an active stream or pending approval", async () => {
  seed();
  chatStore.appendUserMessage(source, {
    id: "pause",
    role: "assistant",
    content: "",
    timestamp: 6,
    hitlData: {
      action_requests: [{ name: "execute", args: {} }],
      status: "pending",
      pending_id: "pending",
    },
  });
  const fork = vi.spyOn(octopThreadsApi, "fork");
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  await act(async () => {
    await result.current.editAndResend("ui-user-1", "replacement", "", "agent");
  });
  expect(fork).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled();
  expect(chatStore.getSnapshot(source).messages).toHaveLength(6);
});

it("edits the first user turn into an empty new conversation", async () => {
  seed();
  const fork = vi.spyOn(octopThreadsApi, "fork").mockResolvedValue({
    thread_id: dest,
    session_key: "sk",
    source_thread_id: source,
    copied_messages: 0,
    title: null,
    last_active: 0,
    created_at: 0,
  });
  vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
    thread_id: dest,
    messages: [],
    has_more: false,
  });
  vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  await act(async () => {
    await result.current.editAndResend("ui-user-1", "new first", "", "agent");
  });
  expect(fork).toHaveBeenCalledWith(
    "agent",
    source,
    expect.objectContaining({ user_turns_from_end: 3 }),
  );
  expect(chatStore.getSnapshot(dest).messages.map((m) => m.content)).toEqual([
    "new first",
  ]);
  expect(chatStore.getSnapshot(source).messages).toEqual(messages);
});

it("keeps the source intact and does not send when new history cannot be loaded", async () => {
  seed();
  vi.spyOn(octopThreadsApi, "fork").mockResolvedValue({
    thread_id: dest,
    session_key: "sk",
    source_thread_id: source,
    copied_messages: 2,
    title: null,
    last_active: 0,
    created_at: 0,
  });
  vi.spyOn(octopThreadsApi, "history").mockRejectedValue(
    new Error("history unavailable"),
  );
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  await act(async () => {
    await expect(
      result.current.editAndResend("ui-user-2", "new", "", "agent"),
    ).rejects.toThrow("history unavailable");
  });
  expect(chatStore.getSnapshot(source).messages).toEqual(messages);
  expect(send).not.toHaveBeenCalled();
});

it("blocks editing while tokens are still streaming without cancelling the stream", async () => {
  seed();
  chatStore.ingestHarnessChunk(source, {
    type: "token",
    node: "agent",
    content: "generating",
  });
  const before = chatStore.getSnapshot(source).messages;
  const fork = vi.spyOn(octopThreadsApi, "fork");
  const cancel = vi.spyOn(chatStore, "cancelStream");
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  await act(async () => {
    await result.current.editAndResend("ui-user-1", "new", "", "agent");
  });
  expect(fork).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled();
  expect(cancel).not.toHaveBeenCalled();
  expect(chatStore.getSnapshot(source).messages).toEqual(before);
});

it("waits for the new thread projection before hydrating or sending", async () => {
  seed();
  vi.spyOn(octopThreadsApi, "fork").mockResolvedValue({
    thread_id: dest,
    session_key: "sk",
    source_thread_id: source,
    copied_messages: 2,
    title: null,
    last_active: 0,
    created_at: 0,
  });
  const history = vi
    .spyOn(octopThreadsApi, "history")
    .mockResolvedValueOnce({
      thread_id: dest,
      messages: [],
      history_loading: true,
      history_retry_after_ms: 500,
    })
    .mockResolvedValueOnce({
      thread_id: dest,
      messages: [{ id: "h1", role: "user", content: "prefix" }],
      has_more: false,
    });
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));
  await act(async () => {
    await result.current.editAndResend("ui-user-2", "new", "", "agent");
  });
  expect(history).toHaveBeenCalledTimes(2);
  expect(send).toHaveBeenCalledTimes(1);
  expect(chatStore.getSnapshot(dest).messages.map((m) => m.content)).toEqual([
    "prefix",
    "new",
  ]);
});

it("prevents overlapping edits from creating multiple continuations", async () => {
  seed();
  let resolveFork!: (
    value: Awaited<ReturnType<typeof octopThreadsApi.fork>>,
  ) => void;
  const fork = vi.spyOn(octopThreadsApi, "fork").mockReturnValue(
    new Promise((resolve) => {
      resolveFork = resolve;
    }),
  );
  vi.spyOn(octopThreadsApi, "history").mockResolvedValue({
    thread_id: dest,
    messages: [],
    has_more: false,
  });
  const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
  const { result } = renderHook(() => useChat(source, "agent"));

  await act(async () => {
    const first = result.current.editAndResend("ui-user-1", "new", "", "agent");
    await vi.waitFor(() => expect(fork).toHaveBeenCalledTimes(1));
    await result.current.editAndResend("ui-user-2", "another", "", "agent");
    expect(fork).toHaveBeenCalledTimes(1);
    expect(send).not.toHaveBeenCalled();
    resolveFork({
      thread_id: dest,
      session_key: "sk",
      source_thread_id: source,
      copied_messages: 0,
      title: null,
      last_active: 0,
      created_at: 0,
    });
    await first;
  });

  expect(send).toHaveBeenCalledTimes(1);
  expect(chatStore.getSnapshot(source).messages).toEqual(messages);
});
