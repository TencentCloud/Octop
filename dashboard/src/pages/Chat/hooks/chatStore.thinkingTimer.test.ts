import { afterEach, describe, expect, it } from "vitest";
import { getSnapshot, removeSession, sendTurn } from "./chatStore";

const SESSION = "test-thinking-started-at";

describe("thinkingStartedAt", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("is set when sendTurn starts and cleared when the turn ends", async () => {
    expect(getSnapshot(SESSION).thinkingStartedAt).toBeNull();

    const before = Date.now();
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);
    const snap = getSnapshot(SESSION);
    expect(snap.thinkingStartedAt).not.toBeNull();
    expect(snap.thinkingStartedAt).toBeGreaterThanOrEqual(before);
    expect(snap.isStreaming).toBe(true);

    await turn;

    expect(getSnapshot(SESSION).thinkingStartedAt).toBeNull();
    expect(getSnapshot(SESSION).isStreaming).toBe(false);
  });
});
