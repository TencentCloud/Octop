import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  attachThread,
  isHistoryStale,
  onSessionEvent,
  removeSession,
  setHistoryPage,
} from "./chatStore";
import { MAX_ATTACH_ATTEMPTS } from "./wsResumeGate";

const SESSION = "thr_attach_retry";
const AGENT = "agent-retry";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(): void {}

  close(): void {
    this.closed = true;
  }
}

function attachErrorFrame(retryable: boolean): { data: string } {
  return {
    data: JSON.stringify({
      type: "error",
      op: "subscribe",
      thread_id: SESSION,
      error_code: "thread_not_found",
      retryable,
      message: `thread '${SESSION}' not found`,
    }),
  };
}

function hydrateHistory(): void {
  setHistoryPage(SESSION, [], {
    hasMore: false,
    nextOffset: 0,
    nextCursor: null,
  });
}

async function openSocket(index: number): Promise<FakeWebSocket> {
  const ws = FakeWebSocket.instances[index];
  ws.onopen?.();
  await Promise.resolve();
  return ws;
}

describe("attach retry state machine", () => {
  const sessionEvents: string[] = [];
  let unsubscribe: (() => void) | null = null;

  beforeEach(() => {
    vi.useFakeTimers();
    // Deterministic jitter: attachRetryDelayMs uses ±20 % around the base.
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    FakeWebSocket.instances = [];
    (globalThis as { WebSocket?: unknown }).WebSocket = FakeWebSocket;
    localStorage.setItem("auth_token", "test-token");
    unsubscribe = onSessionEvent((event) => sessionEvents.push(event.kind));
  });

  afterEach(() => {
    removeSession(SESSION);
    unsubscribe?.();
    sessionEvents.length = 0;
    vi.useRealTimers();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("re-attaches with backoff for retryable attach failures", async () => {
    void attachThread(SESSION, AGENT, SESSION);
    expect(FakeWebSocket.instances).toHaveLength(1);

    const first = await openSocket(0);
    first.onmessage?.(attachErrorFrame(true));
    await vi.advanceTimersByTimeAsync(100);
    expect(FakeWebSocket.instances).toHaveLength(2);

    const second = await openSocket(1);
    second.onmessage?.(attachErrorFrame(true));
    await vi.advanceTimersByTimeAsync(200);
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it("gives up after MAX_ATTACH_ATTEMPTS and re-resolves the thread", async () => {
    hydrateHistory();
    void attachThread(SESSION, AGENT, SESSION);

    for (let attempt = 0; attempt < MAX_ATTACH_ATTEMPTS; attempt += 1) {
      const ws = await openSocket(attempt);
      ws.onmessage?.(attachErrorFrame(true));
      await vi.advanceTimersByTimeAsync(100 * 2 ** attempt);
    }

    expect(FakeWebSocket.instances).toHaveLength(MAX_ATTACH_ATTEMPTS + 1);
    const last = await openSocket(MAX_ATTACH_ATTEMPTS);
    last.onmessage?.(attachErrorFrame(true));
    await vi.advanceTimersByTimeAsync(10_000);

    expect(FakeWebSocket.instances).toHaveLength(MAX_ATTACH_ATTEMPTS + 1);
    expect(isHistoryStale(SESSION)).toBe(true);
    expect(sessionEvents).toContain("sessionsChanged");
  });

  it("drops the stale binding immediately for terminal attach failures", async () => {
    hydrateHistory();
    void attachThread(SESSION, AGENT, SESSION);
    const first = await openSocket(0);

    first.onmessage?.(attachErrorFrame(false));
    await vi.advanceTimersByTimeAsync(10_000);

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(isHistoryStale(SESSION)).toBe(true);
    expect(sessionEvents).toContain("sessionsChanged");
  });

  it("cancels a pending re-attach when the session is removed", async () => {
    void attachThread(SESSION, AGENT, SESSION);
    const first = await openSocket(0);

    first.onmessage?.(attachErrorFrame(true));
    removeSession(SESSION);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("supersedes a pending re-attach when a new attach starts", async () => {
    void attachThread(SESSION, AGENT, SESSION);
    const first = await openSocket(0);

    // Retryable failure schedules a 100 ms re-attach, then a fresh attach
    // (navigation / user action) must cancel that timer instead of racing it.
    first.onmessage?.(attachErrorFrame(true));
    void attachThread(SESSION, AGENT, SESSION);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("does not reload history for client-side bad attach requests", async () => {
    hydrateHistory();
    void attachThread(SESSION, AGENT, SESSION);
    const first = await openSocket(0);

    first.onmessage?.({
      data: JSON.stringify({
        type: "error",
        op: "subscribe",
        thread_id: "",
        error_code: "attach_bad_request",
        retryable: false,
        message: "subscribe requires thread_id",
      }),
    });
    await vi.advanceTimersByTimeAsync(10_000);

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(isHistoryStale(SESSION)).toBe(false);
    expect(sessionEvents).not.toContain("sessionsChanged");
  });
});
