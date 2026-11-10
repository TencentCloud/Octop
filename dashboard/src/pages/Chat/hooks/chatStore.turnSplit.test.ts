import { afterEach, expect, it, vi } from "vitest";
import {
  appendUserMessage,
  getSnapshot,
  ingestHarnessChunk,
  onSharedTurnBusy,
  removeSession,
  sendTurn,
  setSessionTeamRoom,
  sharedTurnBlocksSender,
} from "./chatStore";

const SESSION = "turn-split";

afterEach(() => {
  removeSession(SESSION);
  vi.unstubAllGlobals();
});

it("keeps assistant replies from different turns in separate bubbles", () => {
  ingestHarnessChunk(SESSION, {
    type: "token",
    content: "first",
    turn_id: "turn-a",
  });
  ingestHarnessChunk(SESSION, {
    type: "token",
    content: "second",
    turn_id: "turn-b",
  });
  const assistants = getSnapshot(SESSION).messages.filter(
    (message) => message.role === "assistant",
  );
  expect(assistants.map((message) => message.content)).toEqual([
    "first",
    "second",
  ]);
  expect(assistants.map((message) => message.turnId)).toEqual([
    "turn-a",
    "turn-b",
  ]);
});

it("still concatenates tokens that belong to the same turn", () => {
  ingestHarnessChunk(SESSION, {
    type: "token",
    content: "hel",
    turn_id: "turn-a",
  });
  ingestHarnessChunk(SESSION, {
    type: "token",
    content: "lo",
    turn_id: "turn-a",
  });
  expect(
    getSnapshot(SESSION).messages.map((message) => message.content),
  ).toEqual(["hello"]);
});

class Socket {
  static instances: Socket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    Socket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = 1;
      this.onopen?.();
    });
  }
  send(_data: string) {}
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  frame(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

it("blocks another user while a shared turn is running and drops a rejected send", async () => {
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  const notices: string[] = [];
  const unsubscribe = onSharedTurnBusy((event) => {
    notices.push(event.messageId);
  });
  const sent = sendTurn(
    SESSION,
    "question",
    "agent",
    "",
    undefined,
    undefined,
    null,
    SESSION,
  );
  await Promise.resolve();
  const socket = Socket.instances[0];
  socket.frame({ type: "turn.started", turn_id: "live" });
  socket.frame({
    type: "user",
    message_id: "owner-msg",
    content: "question",
    author: { user_id: 7, display_name: "Ada", username: "ada" },
  });
  expect(sharedTurnBlocksSender(SESSION, 8, true)).toBe(true);
  expect(sharedTurnBlocksSender(SESSION, 7, true)).toBe(false);
  expect(sharedTurnBlocksSender(SESSION, 8, false)).toBe(false);

  appendUserMessage(SESSION, {
    id: "other-msg",
    role: "user",
    content: "meanwhile",
    timestamp: 1,
  });
  socket.frame({
    type: "turn.busy",
    message_id: "other-msg",
    reason: "shared_turn_busy",
  });
  expect(
    getSnapshot(SESSION).messages.some((message) => message.id === "other-msg"),
  ).toBe(false);
  expect(notices).toEqual(["other-msg"]);
  expect(getSnapshot(SESSION).isStreaming).toBe(true);

  socket.frame({ type: "turn.ended", turn_id: "live" });
  await sent;
  expect(sharedTurnBlocksSender(SESSION, 8, true)).toBe(false);
  unsubscribe();
});

it("releases the composer when a shared turn rejects the send", async () => {
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  const notices: string[] = [];
  const unsubscribe = onSharedTurnBusy((event) => {
    notices.push(event.messageId);
  });
  const sent = sendTurn(
    SESSION,
    "meanwhile",
    "agent",
    "",
    undefined,
    undefined,
    null,
    SESSION,
    null,
    null,
    null,
    undefined,
    null,
    null,
    null,
    "rejected-msg",
  );
  await Promise.resolve();
  const socket = Socket.instances[0];
  socket.frame({
    type: "turn.busy",
    message_id: "rejected-msg",
    reason: "shared_turn_busy",
  });
  await sent;
  expect(notices).toEqual(["rejected-msg"]);
  expect(getSnapshot(SESSION).isStreaming).toBe(false);
  unsubscribe();
});

it("blocks another user while a shared team member is still speaking", async () => {
  const session = "turn-split-team";
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
  setSessionTeamRoom(session, true);
  const sent = sendTurn(
    session,
    "question",
    "team-host",
    "",
    undefined,
    undefined,
    null,
    session,
  );
  await Promise.resolve();
  const socket = Socket.instances[0];
  socket.frame({ type: "turn.started", turn_id: "host-turn" });
  socket.frame({
    type: "user",
    message_id: "owner-msg",
    content: "question",
    author: { user_id: 7, display_name: "Ada", username: "ada" },
  });
  socket.frame({ type: "turn.ended", turn_id: "host-turn" });
  ingestHarnessChunk(session, {
    type: "token",
    content: "member",
    turn_id: "host-turn",
    agent_id: "member-1",
  });
  expect(sharedTurnBlocksSender(session, 8, true)).toBe(true);
  expect(sharedTurnBlocksSender(session, 7, true)).toBe(false);
  ingestHarnessChunk(session, {
    type: "token",
    content: "next",
    turn_id: "later-turn",
    agent_id: "member-1",
  });
  expect(
    getSnapshot(session)
      .messages.filter((message) => message.speakerAgentId === "member-1")
      .map((message) => message.content),
  ).toEqual(["member", "next"]);
  removeSession(session);
  await sent;
});
