import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import {
  mergeHistoryWithLocalTail,
  preferLocalTranscript,
  serverCaughtUp,
} from "./mergeHistoryTail";

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

  it("drops the live bubbles once the stored user id has a reply", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      msg("local-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "做好了", 5_200),
    ];
    const current = [
      msg("local-user", "user", "继续做", 20_000),
      msg("local-a", "assistant", "做好了", 20_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "local-user", "srv-a"],
    );
  });

  it("keeps the live reply when the user row is stored and the answer is not", () => {
    const loaded = [msg("local-user", "user", "继续做", 5_000)];
    const current = [
      msg("local-user", "user", "继续做", 20_000),
      msg("local-a", "assistant", "正在处理", 20_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["local-user", "local-a"],
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

  it("does not replay a finished turn when the browser clock is ahead", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      msg("local-user", "user", "帮我画一张股权交易的流程图", 5_000),
      msg("srv-a", "assistant", "做好了", 5_200),
    ];
    const current = [
      msg("local-user", "user", "帮我画一张股权交易的流程图", 20_000),
      msg("local-a", "assistant", "帮我画一张股权交易的流程图", 20_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "local-user", "srv-a"],
    );
  });

  it("keeps a second identical send the server page does not have yet", () => {
    const loaded = [
      msg("srv-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "第一次", 5_200),
    ];
    const current = [
      msg("local-user-1", "user", "继续做", 5_000),
      msg("local-a", "assistant", "第一次", 5_100),
      msg("local-user-2", "user", "继续做", 20_000),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["srv-user", "srv-a", "local-user-2"],
    );
  });

  it("keeps a streamed reply when history stored the user turn with the persisted user id", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      msg("local-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "短", 5_100),
    ];
    const current: ChatMessage[] = [
      msg("local-user", "user", "继续做", 5_000),
      {
        ...msg("local-a", "assistant", "短，但是流式里已经更长", 20_100),
        status: "streaming",
      },
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "local-user", "local-a"],
    );
  });

  it("keeps the local assistant when the shared prefix stops at the user message", () => {
    const loaded = [
      msg("m1", "assistant", "之前", 1_000),
      msg("u", "user", "继续做", 5_000),
    ];
    const current: ChatMessage[] = [
      msg("m1", "assistant", "之前", 1_000),
      msg("u", "user", "继续做", 5_000),
      msg("a", "assistant", "已经生成的前半段", 5_100),
    ];
    expect(
      mergeHistoryWithLocalTail(loaded, current).map((m) => m.content),
    ).toEqual(["之前", "继续做", "已经生成的前半段"]);
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
    const current: ChatMessage[] = [
      msg("u", "user", "继续做", 5_000),
      {
        ...msg("local-a", "assistant", "已经写了更长的一段回复", 5_300),
        status: "streaming",
      },
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

  it("keeps a new identical send even when its clock matches the stored turn", () => {
    const loaded = [msg("u1", "user", "继续"), msg("a1", "assistant", "完成")];
    const current = [msg("u2", "user", "继续")];
    expect(mergeHistoryWithLocalTail(loaded, current)).toEqual([
      ...loaded,
      ...current,
    ]);
  });

  it("keeps the richer reply across a live tool gap, then retires it on completion", () => {
    const loaded = [msg("u", "user", "继续"), msg("srv-a", "assistant", "短")];
    const current: ChatMessage[] = [
      msg("u", "user", "继续"),
      { ...msg("local-a", "assistant", "更完整的本地回复"), status: "done" },
    ];
    expect(mergeHistoryWithLocalTail(loaded, current, true)).toEqual(current);
    expect(mergeHistoryWithLocalTail(loaded, current, false)).toEqual(loaded);
  });

  it("does not replace newer server turns with an older cached stream", () => {
    const loaded = [
      msg("u1", "user", "继续"),
      msg("a1", "assistant", "短"),
      msg("u2", "user", "新一轮"),
      msg("a2", "assistant", "完成"),
    ];
    const current: ChatMessage[] = [
      loaded[0],
      {
        ...msg("local-a", "assistant", "旧缓存里的很长很长的回复"),
        status: "streaming",
      },
    ];
    expect(mergeHistoryWithLocalTail(loaded, current)).toEqual(loaded);
    expect(serverCaughtUp(loaded, current)).toBe(true);
  });
});

describe("cached transcript reconciliation", () => {
  it("restores a richer cached reply by id despite timestamp or display text differences", () => {
    const memory = [msg("u", "user", "", 20_000)];
    const cached: ChatMessage[] = [
      msg("u", "user", "附件", 5_000),
      { ...msg("a", "assistant", "已经生成的内容"), status: "streaming" },
    ];
    expect(preferLocalTranscript(memory, cached)).toEqual([
      memory[0],
      cached[1],
    ]);
    expect(serverCaughtUp(memory, cached)).toBe(false);
  });

  it("ignores a cache for a different id with identical text and timestamp", () => {
    const memory = [msg("u2", "user", "继续")];
    const cached = [msg("u1", "user", "继续"), msg("a", "assistant", "旧回复")];
    expect(preferLocalTranscript(memory, cached)).toBe(memory);
    expect(serverCaughtUp(memory, cached)).toBe(false);
  });

  it("keeps a longer cached stream until server history catches up", () => {
    const loaded = [msg("u", "user", "继续"), msg("srv-a", "assistant", "短")];
    const cached: ChatMessage[] = [
      msg("u", "user", "继续", 20_000),
      {
        ...msg("local-a", "assistant", "短，但是已经更长"),
        status: "streaming",
      },
    ];
    expect(serverCaughtUp(loaded, cached)).toBe(false);
    const complete = [loaded[0], { ...loaded[1], content: cached[1].content }];
    expect(serverCaughtUp(complete, cached)).toBe(true);
    expect(mergeHistoryWithLocalTail(complete, cached)).toEqual(complete);
  });

  it("retires finished cached bubbles even when they are longer than the server reply", () => {
    const loaded = [
      msg("u", "user", "继续"),
      msg("srv-a", "assistant", "完成"),
    ];
    const cached: ChatMessage[] = [
      msg("u", "user", "继续", 20_000),
      {
        ...msg("local-a", "assistant", "旧的本地内容比最终回复长"),
        status: "done",
      },
    ];
    expect(serverCaughtUp(loaded, cached)).toBe(true);
    expect(mergeHistoryWithLocalTail(loaded, cached)).toEqual(loaded);
  });
});
