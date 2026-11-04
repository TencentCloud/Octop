import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearInflightTail,
  flushInflightTail,
  readInflightTail,
  scheduleInflightTail,
  moveInflightTail,
  saveRecoveryMessages,
  readRecoveryMessages,
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
  saveRecoveryMessages(thread, []);
  vi.useRealTimers();
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
    expect(readInflightTail(thread)?.[0].content).toBe("ab");
    expect(
      sessionStorage.getItem(`octop:inflight-transcript:${thread}`),
    ).toBeNull();
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

it("preserves every unconfirmed turn and user attachments across reload", () => {
  const attachments: ChatMessage["attachments"] = [
    {
      url: "",
      workspacePath: "inbound/photo.png",
      filename: "photo.png",
      kind: "image",
    },
  ];
  flushInflightTail(thread, [
    {
      ...msg("u1", "user", "first"),
      delivery: "accepted",
      attachments,
      turnId: "turn1",
    },
    msg("a1", "assistant", "reply"),
    { ...msg("u2", "user", "second"), delivery: "pending" },
  ]);
  expect(readInflightTail(thread)?.map((m) => m.id)).toEqual([
    "u1",
    "a1",
    "u2",
  ]);
  expect(readInflightTail(thread)?.[0].attachments).toEqual(attachments);
  expect(readInflightTail(thread)?.[0].delivery).toBe("accepted");
});

it("retains uncertain recovery when a new turn overwrites the active cache", () => {
  const uncertain = [msg("u-old", "user", "do not lose this")];
  saveRecoveryMessages(thread, uncertain);
  flushInflightTail(thread, [msg("u-new", "user", "new send")]);
  expect(readRecoveryMessages(thread)?.[0].content).toBe("do not lose this");
});

it("keeps the last stored copy if sessionStorage rejects an update", () => {
  flushInflightTail(thread, [msg("u", "user", "saved")]);
  const failingWrite = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementationOnce(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
  flushInflightTail(thread, [msg("u", "user", "newer")]);
  failingWrite.mockRestore();
  expect(readInflightTail(thread)?.[0].content).toBe("saved");
});

it("does not overwrite recovery after its first storage update fails", () => {
  const old = [msg("old", "user", "old uncertain text")];
  flushInflightTail(thread, old);
  const failingWrite = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementationOnce(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
  saveRecoveryMessages(thread, old);
  flushInflightTail(thread, [msg("new", "user", "new send")]);
  failingWrite.mockRestore();
  const envelope = JSON.parse(
    sessionStorage.getItem(`octop:inflight-transcript:${thread}`)!,
  );
  expect(envelope.recovery.map((m: ChatMessage) => m.id)).toEqual(["old"]);
  expect(envelope.tail.map((m: ChatMessage) => m.id)).toEqual(["new"]);
});

it("moves active sends and uncertain recovery together when a thread ID is resolved", () => {
  const destination = `${thread}-resolved`;
  try {
    saveRecoveryMessages(thread, [msg("old", "user", "uncertain")]);
    scheduleInflightTail(thread, [
      { ...msg("pending", "user", "new send"), delivery: "pending" },
    ]);
    moveInflightTail(thread, destination);
    expect(readInflightTail(destination)?.[0].id).toBe("pending");
    expect(readRecoveryMessages(destination)?.[0].id).toBe("old");
    expect(readInflightTail(thread)).toBeNull();
    expect(readRecoveryMessages(thread)).toEqual([]);
  } finally {
    clearInflightTail(destination);
    saveRecoveryMessages(destination, []);
  }
});
