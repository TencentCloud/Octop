import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearInflightTail,
  flushInflightTail,
  readInflightTail,
  scheduleInflightTail,
} from "./inflightTranscriptCache";
import type { ChatMessage } from "../hooks/sseHelpers";

const thread = "inflight-cache-test";

function msg(
  id: string,
  role: ChatMessage["role"],
  content: string,
): ChatMessage {
  return { id, role, content, timestamp: 1, status: "streaming" };
}

afterEach(() => {
  clearInflightTail(thread);
});

describe("inflight transcript cache", () => {
  it("preserves the resumed-turn boundary across a storage reload", () => {
    flushInflightTail(thread, [
      { ...msg("old", "assistant", "old answer"), status: "done" },
      { ...msg("resumed", "assistant", "new answer"), startsNewTurn: true },
    ]);
    // readInflightTail decodes sessionStorage on every call.
    expect(
      readInflightTail(thread)?.find((message) => message.id === "resumed")
        ?.startsNewTurn,
    ).toBe(true);
  });
  it("round-trips the current turn and drops earlier history", () => {
    flushInflightTail(thread, [
      msg("old", "assistant", "更早"),
      msg("u", "user", "继续"),
      msg("a", "assistant", "写到这里"),
    ]);
    expect(readInflightTail(thread)?.map((message) => message.id)).toEqual([
      "u",
      "a",
    ]);
  });

  it("keeps the latest tail when tokens arrive inside one write window", () => {
    vi.useFakeTimers();
    scheduleInflightTail(thread, [msg("u", "user", "a")]);
    scheduleInflightTail(thread, [msg("u", "user", "ab")]);
    expect(readInflightTail(thread)).toBeNull();
    vi.advanceTimersByTime(200);
    expect(readInflightTail(thread)?.map((message) => message.content)).toEqual(
      ["ab"],
    );
    vi.useRealTimers();
  });

  it("clears an empty tail", () => {
    flushInflightTail(thread, [msg("a", "assistant", "只有回复")]);
    flushInflightTail(thread, []);
    expect(readInflightTail(thread)).toBeNull();
  });
});
