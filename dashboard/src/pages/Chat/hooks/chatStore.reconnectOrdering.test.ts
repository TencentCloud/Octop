import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as store from "./chatStore";
import { clearInflightTail } from "../utils/inflightTranscriptCache";

const session = "reconnect-ordering";
class Socket {
  static instances: Socket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor() {
    Socket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = 1;
      this.onopen?.();
    });
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  frame(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  Socket.instances = [];
  vi.stubGlobal("WebSocket", Socket);
});
afterEach(() => {
  store.removeSession(session);
  clearInflightTail(session);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("ignores late frames and close events from a replaced socket", async () => {
  const first = store.sendTurn(
    session,
    "first",
    "agent",
    "",
    undefined,
    undefined,
    null,
    session,
  );
  await Promise.resolve();
  const old = Socket.instances[0];
  old.frame({ type: "turn.started", turn_id: "old" });
  old.frame({ type: "token", content: "first reply" });
  old.frame({ type: "turn.ended", turn_id: "old" });
  await first;
  store.appendUserMessage(session, {
    id: "new-user",
    role: "user",
    content: "next",
    timestamp: 1,
  });
  const second = store.sendTurn(
    session,
    "second",
    "agent",
    "",
    undefined,
    undefined,
    null,
    session,
  );
  await Promise.resolve();
  const current = Socket.instances[1];
  current.frame({
    type: "turn.started",
    turn_id: "new",
  });
  old.frame({ type: "token", content: "ghost old reply" });
  old.frame({ type: "turn.ended", turn_id: "old" });
  old.close();
  current.frame({ type: "turn.ended", turn_id: "old" });
  expect(store.getSnapshot(session).activeTurnId).toBe("new");
  expect(store.getSnapshot(session).isStreaming).toBe(true);
  expect(
    store.getSnapshot(session).messages.find((m) => m.id === "new-user")
      ?.localPending,
  ).toBe(true);
  current.frame({ type: "token", content: "second reply" });
  current.frame({ type: "turn.ended", turn_id: "new" });
  await second;
  expect(store.getSnapshot(session).messages.map((m) => m.content)).toEqual([
    "first reply",
    "next",
    "second reply",
  ]);
});

it("reconnects by subscribing without resending the user message", async () => {
  vi.useFakeTimers();
  const sent = store.sendTurn(
    session,
    "question",
    "agent",
    "",
    undefined,
    undefined,
    null,
    session,
  );
  await Promise.resolve();
  const old = Socket.instances[0];
  old.frame({ type: "token", content: "first" });
  old.close();
  await sent;
  await vi.advanceTimersByTimeAsync(400);
  const resumed = Socket.instances[1];
  expect(resumed).toBeDefined();
  expect(resumed.sent.map((row) => JSON.parse(row).type)).toEqual([
    "subscribe",
  ]);
  resumed.frame({
    type: "turn_status",
    active: true,
    thread_id: session,
  });
  old.frame({ type: "token", content: "ghost" });
  resumed.frame({ type: "token", content: " second" });
  resumed.frame({ type: "done" });
  expect(store.getSnapshot(session).messages.at(-1)?.content).toBe(
    "first second",
  );
  expect(store.getSnapshot(session).isStreaming).toBe(false);
});
