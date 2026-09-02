import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/useChat";
import { groupConsecutiveAssistantMessages } from "./messageGrouping";
import {
  buildTurnTimelineItems,
  mergeTurnPositions,
  readElementDirection,
  resolveActiveTurnId,
  resolveFollowPinnedTurnId,
  tickVisualForDistance,
  truncatePreviewText,
  visibleTurnWindow,
} from "./turnTimeline";

function msg(
  role: ChatMessage["role"],
  id: string,
  extra?: Partial<ChatMessage>,
): ChatMessage {
  return {
    id,
    role,
    content: extra?.content ?? "",
    status: "done",
    timestamp: Date.now(),
    ...extra,
  };
}

const copy = {
  userFallback: "(empty)",
  emptyAssistant: "(no reply)",
  runningAssistant: "(generating)",
};

describe("truncatePreviewText", () => {
  it("falls back when empty", () => {
    expect(truncatePreviewText([], "fallback")).toBe("fallback");
  });

  it("truncates long text with ellipsis", () => {
    const long = "a".repeat(300);
    const out = truncatePreviewText([long], "x", 20);
    expect(out.endsWith("...")).toBe(true);
    expect(out.length).toBeLessThanOrEqual(20);
  });

  it("keeps at most two paragraphs", () => {
    const out = truncatePreviewText(["one\n\ntwo\n\nthree"], "x", 220, 2);
    expect(out).toBe("one\ntwo");
  });
});

describe("tickVisualForDistance", () => {
  it("returns idle when no focus", () => {
    expect(tickVisualForDistance(0, undefined)).toMatchObject({
      tone: "idle",
      scaleX: 1,
    });
  });

  it("peaks at focus and cascades neighbors", () => {
    expect(tickVisualForDistance(3, 3).scaleX).toBe(2.6);
    expect(tickVisualForDistance(2, 3).scaleX).toBe(1.7);
    expect(tickVisualForDistance(1, 3).scaleX).toBe(1.25);
    expect(tickVisualForDistance(0, 3).scaleX).toBe(1);
  });
});

describe("resolveActiveTurnId", () => {
  it("picks the visible row closest to the viewport top", () => {
    const id = resolveActiveTurnId({
      scrollOffsetPx: 100,
      viewportHeightPx: 400,
      positions: [
        { messageId: "a", start: 0, end: 80 },
        { messageId: "b", start: 120, end: 200 },
        { messageId: "c", start: 500, end: 580 },
      ],
    });
    expect(id).toBe("b");
  });

  it("falls back to the last row above the viewport", () => {
    const id = resolveActiveTurnId({
      scrollOffsetPx: 300,
      viewportHeightPx: 100,
      positions: [
        { messageId: "a", start: 0, end: 50 },
        { messageId: "b", start: 100, end: 150 },
        { messageId: "c", start: 500, end: 550 },
      ],
    });
    expect(id).toBe("b");
  });
});

describe("buildTurnTimelineItems", () => {
  it("indexes user turns with assistant previews", () => {
    const messages = [
      msg("user", "u1", { content: "hello" }),
      msg("assistant", "a1", { content: "world" }),
      msg("user", "u2", { content: "again" }),
      msg("assistant", "a2", { content: "ok", status: "streaming" }),
    ];
    const groups = groupConsecutiveAssistantMessages(messages);
    const items = buildTurnTimelineItems(messages, groups, copy, {
      isStreaming: true,
    });
    expect(items).toHaveLength(2);
    expect(items[0]).toMatchObject({
      messageId: "u1",
      userPreview: "hello",
      assistantPreview: "world",
      assistantPreviewKind: "text",
      isRunning: false,
    });
    expect(items[1]).toMatchObject({
      messageId: "u2",
      isRunning: true,
    });
  });
});

describe("mergeTurnPositions", () => {
  it("interpolates missing virtualized turns from neighbors", () => {
    const merged = mergeTurnPositions({
      estimatedUnitHeight: 100,
      turns: [
        { messageId: "u1", groupIndex: 0 },
        { messageId: "u2", groupIndex: 2 },
        { messageId: "u3", groupIndex: 4 },
      ],
      measured: [{ messageId: "u1", start: 0, end: 80 }],
    });
    expect(merged[0]).toEqual({ messageId: "u1", start: 0, end: 80 });
    expect(merged[1].start).toBe(200);
    expect(merged[2].start).toBe(400);
  });
});

describe("resolveFollowPinnedTurnId", () => {
  it("pins to the latest turn while following", () => {
    expect(
      resolveFollowPinnedTurnId([{ messageId: "a" }, { messageId: "b" }], {
        following: true,
      }),
    ).toBe("b");
    expect(
      resolveFollowPinnedTurnId([{ messageId: "a" }], { following: false }),
    ).toBeUndefined();
  });
});

describe("visibleTurnWindow", () => {
  it("returns full range when forceFull", () => {
    expect(
      visibleTurnWindow({
        count: 100,
        scrollTop: 0,
        viewportHeight: 100,
        forceFull: true,
      }),
    ).toEqual({ start: 0, end: 100 });
  });

  it("windows ticks with overscan", () => {
    expect(
      visibleTurnWindow({
        count: 100,
        scrollTop: 140,
        viewportHeight: 70,
        rowPx: 14,
        overscan: 2,
      }),
    ).toEqual({ start: 8, end: 17 });
  });
});

describe("readElementDirection", () => {
  it("reads rtl from document dir", () => {
    document.documentElement.setAttribute("dir", "rtl");
    expect(readElementDirection(null)).toBe("rtl");
    document.documentElement.setAttribute("dir", "ltr");
    expect(readElementDirection(null)).toBe("ltr");
  });
});
