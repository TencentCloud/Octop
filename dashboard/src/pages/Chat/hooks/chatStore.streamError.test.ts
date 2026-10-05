import { afterEach, describe, expect, it } from "vitest";
import { getSnapshot, ingestHarnessChunk, removeSession } from "./chatStore";

const SESSION = "test-stream-error-finalize";

describe("finalizeStreamingMessages stream-error promotion", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("does not promote a normal answer that mentions rate limits", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "If you hit Error code: 429 rate_limit, wait a minute.",
    });
    ingestHarnessChunk(SESSION, { type: "done" });
    const msgs = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.status).toBe("done");
  });

  it("promotes model-retry envelopes to error", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "Model call failed after 3 attempts with RuntimeError: boom",
    });
    ingestHarnessChunk(SESSION, { type: "done" });
    const msgs = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.status).toBe("error");
    expect(msgs[0]?.errorInfo).toEqual({
      code: "stream_error",
      source: "model_retry",
    });
  });
});
