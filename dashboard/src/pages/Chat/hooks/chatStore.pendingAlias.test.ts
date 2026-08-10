import { afterEach, describe, expect, it } from "vitest";
import {
  appendUserMessage,
  detachSessionKey,
  getSnapshot,
  removeSession,
  renameSessionKey,
  setMessages,
  type ChatMessage,
} from "./chatStore";
import { PENDING_THREAD_ID } from "../constants";

function makeMessage(id: string, content = `message ${id}`): ChatMessage {
  return { id, role: "user", content, timestamp: Date.now() };
}

describe("renameSessionKey pending alias", () => {
  const tid1 = "thr_alias_test_1";
  const tid2 = "thr_alias_test_2";

  afterEach(() => {
    removeSession(PENDING_THREAD_ID);
    removeSession(tid1);
    removeSession(tid2);
  });

  it("does not let a reused __pending__ key mutate a renamed thread", async () => {
    appendUserMessage(PENDING_THREAD_ID, makeMessage("u1", "first chat"));
    renameSessionKey(PENDING_THREAD_ID, tid1);

    expect(getSnapshot(tid1).messages).toHaveLength(1);
    expect(getSnapshot(tid1).messages[0]?.content).toBe("first chat");

    // Simulate the next "New Chat" before/without waiting for the microtask
    // detach — explicit detachSessionKey is what useChatSend does.
    detachSessionKey(PENDING_THREAD_ID);
    setMessages(PENDING_THREAD_ID, [makeMessage("u2", "second chat")]);

    expect(getSnapshot(tid1).messages).toHaveLength(1);
    expect(getSnapshot(tid1).messages[0]?.content).toBe("first chat");
    expect(getSnapshot(PENDING_THREAD_ID).messages).toHaveLength(1);
    expect(getSnapshot(PENDING_THREAD_ID).messages[0]?.content).toBe(
      "second chat",
    );

    renameSessionKey(PENDING_THREAD_ID, tid2);
    expect(getSnapshot(tid1).messages[0]?.content).toBe("first chat");
    expect(getSnapshot(tid2).messages[0]?.content).toBe("second chat");

    // Microtask should drop the pending alias without touching canonical ids.
    await Promise.resolve();
    expect(getSnapshot(PENDING_THREAD_ID).messages).toHaveLength(0);
    expect(getSnapshot(tid2).messages[0]?.content).toBe("second chat");
  });

  it("microtask detach prevents shared-state bleed after rename alone", async () => {
    appendUserMessage(PENDING_THREAD_ID, makeMessage("u1", "only chat"));
    renameSessionKey(PENDING_THREAD_ID, tid1);
    await Promise.resolve();

    // PENDING is gone; getOrCreate via setMessages starts a fresh bucket.
    setMessages(PENDING_THREAD_ID, [makeMessage("u2", "fresh pending")]);

    expect(getSnapshot(tid1).messages[0]?.content).toBe("only chat");
    expect(getSnapshot(PENDING_THREAD_ID).messages[0]?.content).toBe(
      "fresh pending",
    );
  });
});
