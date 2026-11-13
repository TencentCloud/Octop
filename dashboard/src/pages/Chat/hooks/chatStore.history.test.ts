import { afterEach, describe, expect, it } from "vitest";
import {
  getSnapshot,
  ingestHarnessChunk,
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

describe("setHistoryPage with a still-running server turn (issue #2616)", () => {
  const REFRESH_SESSION = "test-refresh-turn-recovery";

  afterEach(() => {
    removeSession(REFRESH_SESSION);
  });

  function doneAssistant(id: string, content: string): ChatMessage {
    return {
      id,
      role: "assistant",
      content,
      status: "done",
      timestamp: Date.now(),
    };
  }

  it("reopening: live token opens a new bubble instead of appending into the last done assistant", () => {
    const userTurn: ChatMessage = {
      id: "u1",
      role: "user",
      content: "last question",
      timestamp: Date.now(),
    };
    setHistoryPage(
      REFRESH_SESSION,
      [userTurn, doneAssistant("a1", "previous answer")],
      { hasMore: false, nextOffset: 0, turnActive: true },
    );

    ingestHarnessChunk(REFRESH_SESSION, {
      type: "token",
      content: "new turn streaming content",
    } as never);

    const { messages } = getSnapshot(REFRESH_SESSION);
    expect(messages).toHaveLength(3);
    const historical = messages.find((m) => m.id === "a1");
    expect(historical?.content).toBe("previous answer");
    expect(historical?.status).toBe("done");
    const fresh = messages[messages.length - 1];
    expect(fresh.content).toBe("new turn streaming content");
    expect(fresh.status).toBe("streaming");
  });

  it("without the flag the token still continues the wall (existing behavior is unchanged for normal loads)", () => {
    const userTurn: ChatMessage = {
      id: "u1",
      role: "user",
      content: "last question",
      timestamp: Date.now(),
    };
    setHistoryPage(
      REFRESH_SESSION,
      [userTurn, { ...doneAssistant("a1", "previous answer"), status: "streaming" }],
      { hasMore: false, nextOffset: 0 },
    );

    ingestHarnessChunk(REFRESH_SESSION, {
      type: "token",
      content: " continues",
    } as never);

    const { messages } = getSnapshot(REFRESH_SESSION);
    expect(messages).toHaveLength(2);
    expect(messages[1].content).toBe("previous answer continues");
  });

  it("clears recovery once the turn ends", () => {
    setHistoryPage(REFRESH_SESSION, [doneAssistant("a1", "previous answer")], {
      hasMore: false,
      nextOffset: 0,
      turnActive: true,
    });

    ingestHarnessChunk(REFRESH_SESSION, {
      type: "token",
      content: "fresh turn",
    } as never);
    ingestHarnessChunk(REFRESH_SESSION, {
      type: "turn.ended",
    } as never);
    ingestHarnessChunk(REFRESH_SESSION, {
      type: "token",
      content: "second turn",
    } as never);

    const { messages } = getSnapshot(REFRESH_SESSION);
    // The second bubble becomes the continue target after the turn ended.
    expect(messages).toHaveLength(2);
    expect(messages[messages.length - 1].content).toBe("fresh turnsecond turn");
  });
});
