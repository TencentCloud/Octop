import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import type { TFunction } from "i18next";
import {
  Link,
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import * as chatStore from "./chatStore";
import { useChat } from "./useChat";
import { useChatSend } from "./useChatSend";
import { resetSessionStoreForTests, useSessions } from "./useSessions";

const agentId = "expert";
const oldId = "thr_old";
const firstId = "thr_first";
const secondId = "thr_second";
const translate = ((key: string, fallback?: string) =>
  fallback ?? key) as TFunction;

type UserTurn = { type: "user_turn"; text: string; thread_id: string };

class Socket {
  static OPEN = 1;
  static turns: { frame: UserTurn; socket: Socket }[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor() {
    queueMicrotask(() => {
      this.readyState = Socket.OPEN;
      this.onopen?.();
    });
  }

  send(raw: string) {
    const frame = JSON.parse(raw) as UserTurn;
    if (frame.type === "user_turn") Socket.turns.push({ frame, socket: this });
  }

  receive(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}

function pendingCreation() {
  let resolve!: (value: { thread_id: string; session_key: string }) => void;
  const promise = new Promise<{ thread_id: string; session_key: string }>(
    (done) => {
      resolve = done;
    },
  );
  return {
    promise,
    finish: (id: string) =>
      resolve({ thread_id: id, session_key: "dashboard" }),
  };
}

function Chat() {
  const { threadId = "" } = useParams();
  const navigate = useNavigate();
  const { sendMessage, messages, isStreaming } = useChat(
    threadId || null,
    agentId,
  );
  const { createSession } = useSessions(agentId);
  const { handleSend } = useChatSend({
    resolvedAgentId: agentId,
    activeThreadId: threadId || null,
    selectedModel: null,
    selectedConnectors: [],
    selectedKnowledgeBaseIds: [],
    reasoningMode: "auto",
    reasoningEffort: null,
    sendMessage,
    createSession,
    t: translate,
  });
  return (
    <>
      <output data-testid="thread">{threadId}</output>
      <output data-testid="streaming">{String(isStreaming)}</output>
      <output data-testid="transcript">
        {messages.map((message) => message.content).join("\n")}
      </output>
      <Link to={`/chat/${agentId}`}>New chat</Link>
      <Link to={`/chat/${agentId}/${oldId}`}>Old chat</Link>
      <button onClick={() => navigate(-1)}>Back</button>
      <button onClick={() => handleSend("First question")}>Send first</button>
      <button onClick={() => handleSend("Second question")}>Send second</button>
    </>
  );
}

async function openChat() {
  await act(async () => {
    render(
      <MemoryRouter
        initialEntries={[`/chat/${agentId}/${oldId}`]}
        useTransitions={false}
      >
        <Routes>
          <Route path="/chat/:agentId/:threadId?" element={<Chat />} />
        </Routes>
      </MemoryRouter>,
    );
  });
}

async function click(role: "button" | "link", name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole(role, { name }));
  });
}

describe("new chat turn routing", () => {
  beforeEach(() => {
    Socket.turns = [];
    resetSessionStoreForTests();
    vi.stubGlobal("WebSocket", Socket);
    vi.spyOn(octopThreadsApi, "list").mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
    for (const id of [oldId, firstId, secondId, "__empty__"])
      chatStore.removeSession(id);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps the old reply streaming while the new composer sends with the id returned by create", async () => {
    const creation = pendingCreation();
    vi.spyOn(octopThreadsApi, "create").mockReturnValue(creation.promise);
    await openChat();
    await click("button", "Send first");
    const oldSocket = Socket.turns[0].socket;
    expect(Socket.turns[0].frame.thread_id).toBe(oldId);
    await act(async () => {
      oldSocket.receive({
        type: "turn.started",
        thread_id: oldId,
        turn_id: "old-turn",
      });
      oldSocket.receive({
        type: "token",
        thread_id: oldId,
        content: "Part one of A. ",
      });
    });

    await click("link", "New chat");
    expect(screen.getByTestId("streaming")).toHaveTextContent("false");
    await click("button", "Send second");
    expect(Socket.turns).toHaveLength(1);
    expect(screen.getByTestId("transcript")).toHaveTextContent(
      "Second question",
    );
    await act(async () => creation.finish(firstId));
    expect(Socket.turns.map(({ frame }) => frame.thread_id)).toEqual([
      oldId,
      firstId,
    ]);
    expect(oldSocket.readyState).toBe(Socket.OPEN);
    expect(screen.getByTestId("thread")).toHaveTextContent(firstId);

    await act(async () => {
      oldSocket.receive({
        type: "token",
        thread_id: oldId,
        content: "Part two of A.",
      });
      oldSocket.receive({
        type: "turn.ended",
        thread_id: oldId,
        turn_id: "old-turn",
      });
      const newSocket = Socket.turns[1].socket;
      newSocket.receive({
        type: "turn.started",
        thread_id: firstId,
        turn_id: "new-turn",
      });
      newSocket.receive({
        type: "token",
        thread_id: firstId,
        content: "Reply from B.",
      });
      newSocket.receive({
        type: "turn.ended",
        thread_id: firstId,
        turn_id: "new-turn",
      });
    });
    expect(screen.getByTestId("transcript")).toHaveTextContent("Reply from B.");
    expect(screen.getByTestId("transcript")).not.toHaveTextContent(
      "Part two of A.",
    );
    await click("link", "Old chat");
    expect(screen.getByTestId("transcript")).toHaveTextContent(
      "Part two of A.",
    );
    expect(screen.getByTestId("transcript")).not.toHaveTextContent(
      "Reply from B.",
    );
  });

  it("keeps two pending chats separate when their create responses arrive in reverse order", async () => {
    const first = pendingCreation();
    const second = pendingCreation();
    vi.spyOn(octopThreadsApi, "create")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    await openChat();
    await click("link", "New chat");
    await click("button", "Send first");
    const firstPendingId = screen.getByTestId("thread").textContent ?? "";
    await click("link", "New chat");
    await click("button", "Send second");
    const secondPendingId = screen.getByTestId("thread").textContent ?? "";

    expect(firstPendingId).toBeTruthy();
    expect(secondPendingId).toBeTruthy();
    expect(firstPendingId).not.toBe(secondPendingId);
    expect(Socket.turns).toHaveLength(0);

    await act(async () => second.finish(secondId));
    await act(async () => first.finish(firstId));
    expect(
      Socket.turns.map(({ frame }) => [frame.thread_id, frame.text]),
    ).toEqual([
      [secondId, "Second question"],
      [firstId, "First question"],
    ]);
    expect(chatStore.getSnapshot(firstId).messages[0]?.content).toBe(
      "First question",
    );
    expect(chatStore.getSnapshot(secondId).messages[0]?.content).toBe(
      "Second question",
    );
    expect(screen.getByTestId("thread")).toHaveTextContent(secondId);
  });

  it("reopens the created conversation when going back to its temporary route", async () => {
    const creation = pendingCreation();
    vi.spyOn(octopThreadsApi, "create").mockReturnValue(creation.promise);
    await openChat();
    await click("link", "New chat");
    await click("button", "Send first");
    await click("link", "Old chat");

    await act(async () => creation.finish(firstId));
    expect(screen.getByTestId("thread")).toHaveTextContent(oldId);
    expect(Socket.turns.map(({ frame }) => frame.thread_id)).toEqual([firstId]);

    await click("button", "Back");
    expect(screen.getByTestId("thread")).toHaveTextContent(firstId);
    expect(screen.getByTestId("transcript")).toHaveTextContent(
      "First question",
    );
    expect(Socket.turns).toHaveLength(1);
  });
});
