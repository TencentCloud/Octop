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
  vi.restoreAllMocks();
  vi.useRealTimers();
  clearInflightTail(thread);
});

describe("inflight transcript cache", () => {
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
    expect(readInflightTail(thread)?.map((message) => message.content)).toEqual(
      ["ab"],
    );
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

  it("keeps every pending send but never restores the in-memory pending marker", () => {
    flushInflightTail(thread, [
      msg("old", "assistant", "history"),
      { ...msg("u1", "user", "first"), localPending: true },
      msg("a1", "assistant", "partial"),
      { ...msg("u2", "user", "second"), localPending: true },
    ]);
    const cached = readInflightTail(thread)!;
    expect(cached.map((message) => message.id)).toEqual(["u1", "a1", "u2"]);
    expect(cached.every((message) => !message.localPending)).toBe(true);
  });

  it("retains user text and attachments across a refresh", () => {
    const user = {
      ...msg("u", "user", "x".repeat(90000)),
      attachments: [
        { url: "/api/file", filename: "notes.txt", kind: "file" as const },
      ],
    };
    flushInflightTail(thread, [user]);
    expect(readInflightTail(thread)?.[0].content).toBe(user.content);
    expect(readInflightTail(thread)?.[0].attachments).toEqual(user.attachments);
  });

  it("keeps the last successful cache if storage is full or a later tail is too large", () => {
    flushInflightTail(thread, [msg("u", "user", "keep")]);
    const set = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("quota");
      });
    flushInflightTail(thread, [msg("new", "user", "new")]);
    expect(readInflightTail(thread)?.[0].content).toBe("keep");
    set.mockRestore();
    flushInflightTail(thread, [msg("huge", "user", "x".repeat(1600000))]);
    expect(readInflightTail(thread)?.[0].content).toBe("keep");
  });
});
