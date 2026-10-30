import { afterEach, describe, expect, it, vi } from "vitest";
import { groupConsecutiveAssistantMessages } from "../utils/messageGrouping";
import {
  attachThread,
  getSnapshot,
  removeSession,
  prependHistoryMessages,
  setMessages,
  setSessionTeamRoom,
  type ChatMessage,
} from "./chatStore";

const SESSION = "test-resume-history";

class FakeSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static latest: FakeSocket;
  readyState = FakeSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];

  constructor(_url: string) {
    FakeSocket.latest = this;
    queueMicrotask(() => {
      this.readyState = FakeSocket.OPEN;
      this.onopen?.();
    });
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.();
  }
  emit(frame: Record<string, unknown>) {
    this.onmessage?.({
      data: JSON.stringify({ ...frame, thread_id: "thread-one" }),
    });
  }
}

function history(): ChatMessage[] {
  return [
    { id: "old-user", role: "user", content: "old question", timestamp: 1 },
    {
      id: "old-answer",
      role: "assistant",
      content: "old answer",
      status: "done",
      timestamp: 2,
    },
  ];
}

async function subscribe(messages = history()) {
  vi.stubGlobal("WebSocket", FakeSocket);
  setMessages(SESSION, messages);
  await attachThread(SESSION, "host", "thread-one");
  const socket = FakeSocket.latest;
  expect(socket.sent.map((frame) => JSON.parse(frame))).toContainEqual({
    type: "subscribe",
    thread_id: "thread-one",
  });
  socket.emit({ type: "turn_status", active: true });
  return socket;
}

afterEach(() => {
  removeSession(SESSION);
  vi.unstubAllGlobals();
});

describe("subscribing to a turn missing from completed history", () => {
  it("keeps the boundary at the live tail when older history is prepended", async () => {
    const socket = await subscribe();
    prependHistoryMessages(
      SESSION,
      [
        {
          id: "older-answer",
          role: "assistant",
          content: "older page",
          status: "done",
          timestamp: 0,
        },
      ],
      { hasMore: false, nextOffset: 3 },
    );
    socket.emit({ type: "token", content: "new answer" });
    const messages = getSnapshot(SESSION).messages;
    expect(messages[0].startsNewTurn).toBeUndefined();
    expect(messages.at(-1)).toMatchObject({
      content: "new answer",
      startsNewTurn: true,
    });
    expect(
      groupConsecutiveAssistantMessages(messages).filter(
        (group) => group.isGroup,
      ),
    ).toHaveLength(3);
  });

  it("keeps a new routing notice off the completed answer", async () => {
    const old = history();
    old[1].decision = { model: "old-router", empty: false, parts: [] };
    const socket = await subscribe(old);
    socket.emit({
      type: "custom",
      data: { kind: "decision", model: "new-router", empty: false, parts: [] },
    });
    socket.emit({ type: "token", content: "new answer" });
    const messages = getSnapshot(SESSION).messages;
    expect(messages[1]).toEqual(old[1]);
    expect(messages).toHaveLength(3);
    expect(messages[2]).toMatchObject({
      content: "new answer",
      decision: { model: "new-router" },
      startsNewTurn: true,
    });
  });

  it("keeps an image-only response off completed history", async () => {
    const socket = await subscribe();
    socket.emit({
      type: "attachment",
      kind: "image",
      url: "/qa-image.png",
      mime_type: "image/png",
    });
    const messages = getSnapshot(SESSION).messages;
    expect(messages[1]).toEqual(history()[1]);
    expect(messages).toHaveLength(3);
    expect(messages[2].startsNewTurn).toBe(true);
    expect(messages[2].attachments).toContainEqual({
      url: "/qa-image.png",
      kind: "image",
      mediaType: "image/png",
      filename: undefined,
    });
  });

  for (const type of ["token", "reasoning"]) {
    it(`isolates new ${type} chunks from the previous completed answer`, async () => {
      const socket = await subscribe();
      socket.emit({ type, content: "new fragment" });
      const messages = getSnapshot(SESSION).messages;
      expect(messages.find((m) => m.id === "old-answer")).toEqual(history()[1]);
      expect(messages).toHaveLength(3);
      expect(
        groupConsecutiveAssistantMessages(messages).filter(
          (group) => group.isGroup,
        ),
      ).toHaveLength(2);
      expect(messages[2].status).toBe("streaming");
      if (type === "token") expect(messages[2].content).toBe("new fragment");
      else
        expect(messages[2].contentBlocks).toEqual([
          { type: "thinking", content: "new fragment" },
        ]);
    });
  }

  it("keeps thinking and subsequent text on the new bubble across repeated status frames", async () => {
    const socket = await subscribe();
    socket.emit({ type: "reasoning", content: "new thought" });
    socket.emit({ type: "turn_status", active: true });
    socket.emit({ type: "token", content: "new " });
    socket.emit({ type: "token", content: "answer" });
    const messages = getSnapshot(SESSION).messages;
    expect(messages[1]).toEqual(history()[1]);
    expect(messages).toHaveLength(3);
    expect(messages[2]).toMatchObject({
      content: "new answer",
      status: "streaming",
      startsNewTurn: true,
    });
    expect(messages[2].contentBlocks).toContainEqual({
      type: "thinking",
      content: "new thought",
    });
  });

  it("does not replace history with a similar-prefix team snapshot", async () => {
    setSessionTeamRoom(SESSION, true);
    const socket = await subscribe();
    socket.emit({
      type: "token",
      content: "old answer plus new text",
      team_snapshot: true,
    });
    const messages = getSnapshot(SESSION).messages;
    expect(messages[1]).toEqual(history()[1]);
    expect(messages).toHaveLength(3);
    expect(messages[2]).toMatchObject({
      content: "old answer plus new text",
      status: "done",
    });
  });

  it("does not append a team wrap-up to a historical wrap-up", async () => {
    setSessionTeamRoom(SESSION, true);
    const old = history();
    old[1].teamWrapup = true;
    const socket = await subscribe(old);
    socket.emit({ type: "token", content: "new wrap-up", team_wrapup: true });
    const messages = getSnapshot(SESSION).messages;
    expect(messages[1]).toEqual(old[1]);
    expect(messages).toHaveLength(3);
    expect(messages[2]).toMatchObject({
      content: "new wrap-up",
      teamWrapup: true,
    });
  });

  it("continues a local streaming tail after reconnect", async () => {
    const old = history();
    old[1].status = "streaming";
    const socket = await subscribe(old);
    socket.emit({ type: "token", content: " continued" });
    expect(getSnapshot(SESSION).messages).toHaveLength(2);
    expect(getSnapshot(SESSION).messages[1].content).toBe(
      "old answer continued",
    );
  });

  it("preserves the existing continuation behavior for pending HITL", async () => {
    const socket = await subscribe([
      ...history(),
      {
        id: "approval",
        role: "assistant",
        content: "",
        timestamp: 3,
        status: "done",
        hitlData: {
          action_requests: [{ name: "execute", args: {} }],
          pending_id: "pending-one",
          status: "pending",
        },
      },
    ]);
    socket.emit({ type: "token", content: " continued" });
    expect(getSnapshot(SESSION).messages).toHaveLength(3);
    expect(getSnapshot(SESSION).messages[1].content).toBe(
      "old answer continued",
    );
  });
});
