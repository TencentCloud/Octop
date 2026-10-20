import { afterEach, describe, expect, it } from "vitest";
import { getSnapshot, ingestHarnessChunk, removeSession } from "./chatStore";

const SESSION = "test-thread-attach-error";

function errorCodes(): string[] {
  return getSnapshot(SESSION).messages
    .map((message) => message.errorInfo?.code)
    .filter((code): code is string => Boolean(code));
}

describe("control-plane attach errors", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("keeps a retryable subscribe failure out of the transcript", () => {
    ingestHarnessChunk(SESSION, {
      type: "error",
      op: "subscribe",
      thread_id: "thr_x",
      error_code: "thread_not_found",
      retryable: true,
      message: "thread 'thr_x' not found",
    });

    expect(getSnapshot(SESSION).messages).toHaveLength(0);
  });

  it("keeps a terminal cancel failure out of the transcript", () => {
    ingestHarnessChunk(SESSION, {
      type: "error",
      op: "cancel",
      thread_id: "thr_x",
      error_code: "thread_agent_mismatch",
      retryable: false,
      message: "thread 'thr_x' does not belong to agent 'other'",
    });

    expect(getSnapshot(SESSION).messages).toHaveLength(0);
  });

  it("still renders turn failures as assistant error bubbles", () => {
    ingestHarnessChunk(SESSION, {
      type: "error",
      message: "model call failed",
    });

    const { messages } = getSnapshot(SESSION);
    expect(messages).toHaveLength(1);
    expect(messages[0]?.errorInfo).toMatchObject({
      code: "stream_error",
      source: "frontend_stream",
    });
    expect(errorCodes()).toEqual(["stream_error"]);
  });
});
