import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import { mergeHistoryWithLocalTail } from "./mergeHistoryTail";

function msg(
  id: string,
  role: ChatMessage["role"],
  content: string,
  timestamp = 1,
): ChatMessage {
  return { id, role, content, timestamp };
}

describe("mergeHistoryWithLocalTail", () => {
  it("keeps a user message sent while the server page was in flight", () => {
    const loaded = [msg("old-a", "assistant", "之前的回复", 1_000)];
    const current = [msg("local-user", "user", "继续做", 5_000)];
    expect(
      mergeHistoryWithLocalTail(loaded, current).map((m) => m.content),
    ).toEqual(["之前的回复", "继续做"]);
  });

  it("keeps the in-flight assistant bubbles that follow that user message", () => {
    const loaded = [msg("old-a", "assistant", "之前的回复", 1_000)];
    const current = [
      msg("local-user", "user", "继续做", 5_000),
      msg("local-a", "assistant", "正在处理", 5_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "local-user", "local-a"],
    );
  });

  it("keeps a streamed reply when history stored the user turn under new ids", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      msg("srv-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "短", 5_100),
    ];
    const current = [
      msg("local-user", "user", "继续做", 5_000),
      msg("local-a", "assistant", "短，但是流式里已经更长", 5_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "srv-user", "local-a"],
    );
  });

  it("keeps the local assistant when the shared prefix stops at the user message", () => {
    const loaded = [
      msg("m1", "assistant", "之前", 1_000),
      msg("u", "user", "继续做", 5_000),
    ];
    const current = [
      msg("m1", "assistant", "之前", 1_000),
      msg("u", "user", "继续做", 5_000),
      msg("a", "assistant", "已经生成的前半段", 5_100),
    ];
    expect(
      mergeHistoryWithLocalTail(loaded, current).map((m) => m.content),
    ).toEqual(["之前", "继续做", "已经生成的前半段"]);
  });

  it("does not duplicate a turn the server already stored under new ids", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      msg("srv-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "做好了", 5_200),
    ];
    const current = [
      msg("local-user", "user", "继续做", 5_000),
      msg("local-a", "assistant", "做好了", 5_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "srv-user", "srv-a"],
    );
  });

  it("keeps a second send of the same text", () => {
    const loaded = [
      msg("u1", "user", "继续做", 1_000),
      msg("a1", "assistant", "第一次", 1_100),
    ];
    const current = [
      msg("u1", "user", "继续做", 1_000),
      msg("a1", "assistant", "第一次", 1_100),
      msg("local-user", "user", "继续做", 9_000),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["u1", "a1", "local-user"],
    );
  });

  it("keeps a longer assistant reply when the server turn is mostly tool output", () => {
    const loaded = [
      msg("u", "user", "继续做", 5_000),
      {
        ...msg("tool", "tool", "x".repeat(400), 5_100),
        toolData: { name: "shell", output: "x".repeat(400) },
      },
      msg("srv-a", "assistant", "短", 5_200),
    ];
    const current = [
      msg("u", "user", "继续做", 5_000),
      msg("local-a", "assistant", "已经写了更长的一段回复", 5_300),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["u", "local-a"],
    );
  });

  it("keeps older pages already prepended above the latest server page", () => {
    const loaded = [msg("m2", "user", "第二页", 2_000)];
    const current = [
      msg("m1", "user", "更早", 1_000),
      msg("m2", "user", "第二页", 2_000),
      msg("local-user", "user", "新的", 8_000),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["m1", "m2", "local-user"],
    );
  });
});
