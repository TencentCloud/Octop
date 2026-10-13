import { afterEach, describe, expect, it } from "vitest";
import {
  getSnapshot,
  invalidateHistory,
  isHistoryStale,
  prependHistoryMessages,
  removeSession,
  setHistoryPage,
  type ChatMessage,
} from "./chatStore";

const SESSION = "test-thread-history";

function makeMessage(id: string): ChatMessage {
  return {
    id,
    role: "user",
    content: `message ${id}`,
    timestamp: Date.now(),
  };
}

describe("prependHistoryMessages", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("skips messages whose ids already exist in the session", () => {
    setHistoryPage(SESSION, [makeMessage("m25"), makeMessage("m26")], {
      hasMore: true,
      nextOffset: 25,
    });

    prependHistoryMessages(
      SESSION,
      [makeMessage("m24"), makeMessage("m25"), makeMessage("m23")],
      { hasMore: true, nextOffset: 50 },
    );

    const ids = getSnapshot(SESSION).messages.map((message) => message.id);
    expect(ids).toEqual(["m24", "m23", "m25", "m26"]);
  });

  it("updates pagination state even when all older messages are duplicates", () => {
    setHistoryPage(SESSION, [makeMessage("m1")], {
      hasMore: true,
      nextOffset: 25,
    });

    prependHistoryMessages(SESSION, [makeMessage("m1")], {
      hasMore: false,
      nextOffset: 50,
    });

    expect(getSnapshot(SESSION).messages).toHaveLength(1);
    expect(getSnapshot(SESSION).historyHasMore).toBe(false);
    expect(getSnapshot(SESSION).historyNextOffset).toBe(50);
  });
});

describe("invalidateHistory", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("marks a hydrated session stale without dropping its messages", () => {
    setHistoryPage(SESSION, [makeMessage("m1")], {
      hasMore: false,
      nextOffset: 1,
    });

    invalidateHistory(SESSION);

    expect(isHistoryStale(SESSION)).toBe(true);
    expect(getSnapshot(SESSION).messages).toHaveLength(1);
    expect(getSnapshot(SESSION).historyHydrated).toBe(true);
  });

  it("clears staleness once the next page lands", () => {
    setHistoryPage(SESSION, [], { hasMore: false, nextOffset: 0 });
    invalidateHistory(SESSION);

    setHistoryPage(SESSION, [makeMessage("m1")], {
      hasMore: false,
      nextOffset: 1,
    });

    expect(isHistoryStale(SESSION)).toBe(false);
  });

  it("ignores sessions that never loaded history", () => {
    invalidateHistory(SESSION);
    expect(isHistoryStale(SESSION)).toBe(false);
  });
});
