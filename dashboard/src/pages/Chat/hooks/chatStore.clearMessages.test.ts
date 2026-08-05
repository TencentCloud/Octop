import { afterEach, describe, expect, it } from "vitest";
import {
  appendUserMessage,
  clearMessages,
  getSnapshot,
  removeSession,
  sendTurn,
  type ChatMessage,
} from "./chatStore";

const SESSION = "test-clear-messages";

function makeMessage(id: string): ChatMessage {
  return { id, role: "user", content: `message ${id}`, timestamp: Date.now() };
}

describe("clearMessages", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("empties an idle session", () => {
    appendUserMessage(SESSION, makeMessage("m1"));

    clearMessages(SESSION);

    expect(getSnapshot(SESSION).messages).toHaveLength(0);
  });

  it("keeps a session that still has a turn in flight", async () => {
    appendUserMessage(SESSION, makeMessage("m1"));
    const turn = sendTurn(SESSION, "hi", "agent-1", "", undefined);
    expect(getSnapshot(SESSION).isStreaming).toBe(true);

    clearMessages(SESSION);

    expect(getSnapshot(SESSION).isStreaming).toBe(true);
    expect(getSnapshot(SESSION).messages).toHaveLength(1);

    await turn;
  });
});
