import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import {
  mergeHistoryWithLocalTail,
  mergeOrderedMessages,
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

function pending(
  id: string,
  role: ChatMessage["role"],
  content: string,
  timestamp = 1,
): ChatMessage {
  return { ...msg(id, role, content, timestamp), delivery: "pending" };
}

describe("mergeHistoryWithLocalTail", () => {
  it("keeps a user message sent while the server page was in flight", () => {
    const loaded = [msg("old-a", "assistant", "之前的回复", 1_000)];
    const current = [pending("local-user", "user", "继续做", 5_000)];
    expect(
      mergeHistoryWithLocalTail(loaded, current).map((m) => m.content),
    ).toEqual(["之前的回复", "继续做"]);
  });

  it("keeps the in-flight assistant bubbles that follow that user message", () => {
    const loaded = [msg("old-a", "assistant", "之前的回复", 1_000)];
    const current = [
      pending("local-user", "user", "继续做", 5_000),
      msg("local-a", "assistant", "正在处理", 5_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "local-user", "local-a"],
    );
  });

  it("drops the live bubbles once the stored user id has a reply", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      pending("local-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "做好了", 5_200),
    ];
    const current = [
      pending("local-user", "user", "继续做", 20_000),
      msg("local-a", "assistant", "做好了", 20_100),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["old-a", "local-user", "srv-a"],
    );
  });

  it("keeps the live reply when the user row is stored and the answer is not", () => {
    const loaded = [pending("local-user", "user", "继续做", 5_000)];
    const current = [
      pending("local-user", "user", "继续做", 20_000),
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
      pending("local-user", "user", "继续做", 9_000),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["u1", "a1", "local-user"],
    );
  });

  it("does not replay a finished turn when the browser clock is ahead", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      pending("local-user", "user", "帮我画一张股权交易的流程图", 5_000),
      msg("srv-a", "assistant", "做好了", 5_200),
    ];
    const current = [
      pending("local-user", "user", "帮我画一张股权交易的流程图", 20_000),
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
      pending("local-user-2", "user", "继续做", 20_000),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["srv-user", "srv-a", "local-user-2"],
    );
  });

  it("keeps a streamed reply when history stored the user turn with the persisted user id", () => {
    const loaded = [
      msg("old-a", "assistant", "之前的回复", 1_000),
      pending("local-user", "user", "继续做", 5_000),
      msg("srv-a", "assistant", "短", 5_100),
    ];
    const current: ChatMessage[] = [
      pending("local-user", "user", "继续做", 5_000),
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
      pending("local-user", "user", "新的", 8_000),
    ];
    expect(mergeHistoryWithLocalTail(loaded, current).map((m) => m.id)).toEqual(
      ["m1", "m2", "local-user"],
    );
  });

  it("keeps a new identical send even when its clock matches the stored turn", () => {
    const loaded = [msg("u1", "user", "继续"), msg("a1", "assistant", "完成")];
    const current = [pending("u2", "user", "继续")];
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
      { ...msg("u1", "user", "继续"), turnStatus: "complete" },
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
    const complete = [
      { ...loaded[0], turnStatus: "complete" },
      { ...loaded[1], content: "Final text may be shorter" },
    ];
    expect(serverCaughtUp(complete, cached)).toBe(true);
    expect(mergeHistoryWithLocalTail(complete, cached)).toEqual(complete);
  });

  it("retires finished cached bubbles even when they are longer than the server reply", () => {
    const loaded = [
      { ...msg("u", "user", "继续"), turnStatus: "complete" },
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

describe("history ordering regressions", () => {
  const latest: ChatMessage[] = [
    { ...msg("u15", "user", "15:01", 100), serverOrder: [2, 50] },
    { ...msg("a15", "assistant", "15:02", 101), serverOrder: [2, 51] },
  ];
  const stale = [
    msg("u11", "user", "11:02", 900_000),
    msg("a11", "assistant", "11:03", 900_001),
  ];

  it("does not append a disconnected cached turn even if its clock is ahead", () => {
    expect(mergeHistoryWithLocalTail(latest, stale)).toEqual(latest);
    expect(
      mergeHistoryWithLocalTail(
        latest,
        [
          { ...stale[0], delivery: "pending" },
          { ...stale[1], status: "streaming" },
        ],
        {
          isStreaming: true,
          pendingUserIds: new Set(),
        },
      ),
    ).toEqual(latest);
  });

  it("keeps two explicit new sends while history is loading", () => {
    const current = [
      pending("new1", "user", "same"),
      msg("live1", "assistant", "partial"),
      pending("new2", "user", "same"),
    ];
    expect(mergeHistoryWithLocalTail(latest, current).map((m) => m.id)).toEqual(
      ["u15", "a15", "new1", "live1", "new2"],
    );
  });

  it("does not append a stored older send just because the latest page omits it", () => {
    expect(
      mergeHistoryWithLocalTail(
        latest,
        [{ ...stale[0], delivery: "accepted" }, stale[1]],
        {
          receipts: {
            u11: { state: "stored", persisted: true, server_order: [2, 1] },
          },
        },
      ),
    ).toEqual(latest);
    expect(
      serverCaughtUp(latest, stale, {
        u11: { state: "stored", persisted: true },
      }),
    ).toBe(true);
  });

  it("uses segment and sequence across non-overlapping pages, regardless of timestamps", () => {
    const older: ChatMessage[] = [
      { ...stale[0], serverOrder: [0, 1] },
      { ...stale[1], serverOrder: [0, 2] },
    ];
    // Latest-page refresh resets a disconnected visible window so its cursor
    // can retrieve the gap; older-page loads use the ordered union below.
    expect(mergeHistoryWithLocalTail(latest, older)).toEqual(latest);
    expect(mergeOrderedMessages(latest, older)).toEqual([...older, ...latest]);
  });

  it("repositions an older duplicate using its canonical server position", () => {
    const misplaced = [...latest, stale[0]];
    expect(
      mergeOrderedMessages(misplaced, [
        { ...stale[0], serverOrder: [0, 1] },
      ]).map((m) => m.id),
    ).toEqual(["u11", "u15", "a15"]);
  });

  it("requires persistence confirmation to retire a stream, never matching text length", () => {
    const cached: ChatMessage[] = [
      msg("u15", "user", "question"),
      {
        ...msg("live", "assistant", "a much longer local reply"),
        status: "streaming",
      },
    ];
    expect(
      serverCaughtUp(latest, cached, {
        u15: { state: "stored", persisted: false },
      }),
    ).toBe(false);
    expect(
      mergeHistoryWithLocalTail(latest, cached, {
        isStreaming: true,
        receipts: { u15: { state: "stored", persisted: true } },
      }),
    ).toEqual(latest);
  });

  it("keeps unverified recovery out of an empty transcript", () => {
    expect(preferLocalTranscript([], stale)).toEqual([]);
  });
});

it("does not move an active stored user behind a page of newer tool records", () => {
  const loaded: ChatMessage[] = [
    { ...msg("tool", "tool", "15:02 tool result"), serverOrder: [2, 30] },
  ];
  const current: ChatMessage[] = [
    pending("u", "user", "11:02 question"),
    { ...msg("local", "assistant", "streamed reply"), status: "streaming" },
  ];
  expect(
    mergeHistoryWithLocalTail(loaded, current, {
      isStreaming: true,
      receipts: {
        u: { state: "active", persisted: false, server_order: [2, 1] },
      },
    }),
  ).toEqual(loaded);
});

it("does not infer contiguous history coverage from an optimistic user ID overlap", () => {
  const current: ChatMessage[] = [
    { ...msg("old-u", "user", "old question"), serverOrder: [2, 1] },
    { ...msg("old-partial", "assistant", "partial"), serverOrder: [2, 2] },
    pending("new-u", "user", "new question"),
  ];
  const loaded: ChatMessage[] = [
    {
      ...msg("new-u", "user", "new question"),
      serverOrder: [2, 40],
      turnStatus: "complete",
    },
    { ...msg("new-a", "assistant", "answer"), serverOrder: [2, 41] },
  ];
  expect(mergeHistoryWithLocalTail(loaded, current)).toEqual(loaded);
});
