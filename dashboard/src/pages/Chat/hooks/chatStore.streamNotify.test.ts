import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getSnapshot,
  ingestHarnessChunk,
  removeSession,
  sendTurn,
  setMessages,
  subscribe,
} from "./chatStore";

const SESSION = "test-stream-notify-coalesce";

function token(text: string) {
  return { type: "token" as const, node: "agent", content: text };
}

describe("streaming notify coalescing", () => {
  afterEach(() => {
    vi.useRealTimers();
    removeSession(SESSION);
  });

  it("delivers one listener call per coalescing window, not one per token", async () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    const unsubscribe = subscribe(SESSION, listener);
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);

    listener.mockClear();
    for (let i = 0; i < 40; i++) {
      ingestHarnessChunk(SESSION, token(`tok-${i} `));
    }
    // 40 tokens must not mean 40 React re-renders.
    expect(listener).not.toHaveBeenCalled();
    vi.advanceTimersByTime(45);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    await turn;
  });

  it("keeps getSnapshot() current while notifications are pending", () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    subscribe(SESSION, listener);
    sendTurn(SESSION, "hi", "agent-1", "", undefined);
    listener.mockClear();

    ingestHarnessChunk(SESSION, token("hello "));
    ingestHarnessChunk(SESSION, token("world"));
    expect(getSnapshot(SESSION).isStreaming).toBe(true);
    expect(getSnapshot(SESSION).messages.at(-1)?.content).toBe("hello world");
  });

  it("flushes the last frame synchronously when the turn ends", async () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(SESSION, listener);
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);
    listener.mockClear();

    ingestHarnessChunk(SESSION, token("partial"));
    ingestHarnessChunk(SESSION, { type: "done" } as never);
    expect(listener).toHaveBeenCalled();
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
    expect(getSnapshot(SESSION).messages.at(-1)?.content).toBe("partial");

    unsubscribe();
    await turn;
  });

  it("cancels a pending coalesced frame when a sync notify lands", () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    subscribe(SESSION, listener);
    sendTurn(SESSION, "hi", "agent-1", "", undefined);
    listener.mockClear();

    ingestHarnessChunk(SESSION, token("streamed"));
    setMessages(SESSION, [
      {
        id: "h1",
        role: "user",
        content: "from history",
        status: "done",
        timestamp: 1,
      },
    ]);
    expect(listener).toHaveBeenCalledTimes(1);
    listener.mockClear();
    vi.advanceTimersByTime(45);
    expect(listener).not.toHaveBeenCalled();
  });
});
