import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getSnapshot,
  ingestHarnessChunk,
  removeSession,
  subscribe,
} from "./chatStore";

const SESSION = "test-stream-paint";

afterEach(() => {
  removeSession(SESSION);
  vi.useRealTimers();
});

describe("stream paint coalescing", () => {
  it("keeps the snapshot current and paints token bursts once", () => {
    vi.useFakeTimers();
    const paints: string[] = [];
    const unsubscribe = subscribe(SESSION, () => {
      const last = getSnapshot(SESSION).messages.at(-1);
      paints.push(last?.content ?? "");
    });

    ingestHarnessChunk(SESSION, { type: "token", content: "Hel" });
    ingestHarnessChunk(SESSION, { type: "token", content: "lo" });
    expect(getSnapshot(SESSION).messages.at(-1)?.content).toBe("Hello");
    expect(paints).toEqual([]);

    vi.advanceTimersByTime(50);
    expect(paints).toEqual(["Hello"]);

    unsubscribe();
  });

  it("paints a following tool or done immediately", () => {
    vi.useFakeTimers();
    let paints = 0;
    const unsubscribe = subscribe(SESSION, () => {
      paints += 1;
    });

    ingestHarnessChunk(SESSION, { type: "token", content: "Hi" });
    expect(paints).toBe(0);
    ingestHarnessChunk(SESSION, { type: "done" });
    expect(paints).toBe(1);
    expect(getSnapshot(SESSION).messages.at(-1)?.status).toBe("done");

    vi.advanceTimersByTime(50);
    expect(paints).toBe(1);

    unsubscribe();
  });
});
