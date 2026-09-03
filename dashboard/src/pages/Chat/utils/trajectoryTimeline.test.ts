import { describe, expect, it } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import {
  deriveSwimlaneSpans,
  orderedRange,
  trajectoryFocusEventIds,
  zoomDomain,
  type SwimlaneSpan,
} from "./trajectoryTimeline";

function event(
  overrides: Partial<TrajectoryEvent> &
    Pick<TrajectoryEvent, "event_id" | "kind">,
): TrajectoryEvent {
  return {
    thread_id: "T1",
    agent_id: "A1",
    seq: 1,
    ts: 1,
    turn_id: null,
    request_seq: null,
    is_error: false,
    summary: "",
    payload: {},
    ...overrides,
  };
}

describe("deriveSwimlaneSpans", () => {
  it("returns no spans for an empty event list", () => {
    expect(deriveSwimlaneSpans([], "sequence")).toEqual([]);
  });

  it("emits one discrete span per event in sequence mode (no lane merge)", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({ event_id: "u", kind: "user" }),
        event({ event_id: "a", kind: "assistant" }),
        event({ event_id: "t1", kind: "tool" }),
        event({ event_id: "t2", kind: "tool" }),
        event({ event_id: "c", kind: "context" }),
      ],
      "sequence",
    );
    expect(
      spans.map((span) => ({
        lane: span.lane,
        kind: span.kind,
        eventIds: span.eventIds,
        start: span.start,
        end: span.end,
      })),
    ).toEqual([
      {
        lane: "input",
        kind: "user",
        eventIds: ["u"],
        start: 0,
        end: 1,
      },
      {
        lane: "model",
        kind: "assistant",
        eventIds: ["a"],
        start: 1,
        end: 2,
      },
      {
        lane: "tools",
        kind: "tool",
        eventIds: ["t1"],
        start: 2,
        end: 3,
      },
      {
        lane: "tools",
        kind: "tool",
        eventIds: ["t2"],
        start: 3,
        end: 4,
      },
      {
        lane: "input",
        kind: "context",
        eventIds: ["c"],
        start: 4,
        end: 5,
      },
    ]);
  });

  it("sizes spans from payload durations in duration mode", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({
          event_id: "a",
          kind: "assistant",
          payload: { llm_duration_ms: 100 },
        }),
        event({
          event_id: "t",
          kind: "tool",
          payload: { tool_duration_ms: 50 },
        }),
      ],
      "duration",
    );
    expect(spans).toHaveLength(2);
    expect(spans[0]).toMatchObject({
      lane: "model",
      eventIds: ["a"],
      start: 0,
      end: 100,
    });
    expect(spans[1]).toMatchObject({
      lane: "tools",
      eventIds: ["t"],
      start: 100,
      end: 150,
    });
  });

  it("falls back to timestamp gaps in duration mode when payload lacks durations", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({ event_id: "a", kind: "assistant", ts: 1 }),
        event({ event_id: "t", kind: "tool", ts: 1.5 }),
        event({ event_id: "u", kind: "user", ts: 2, summary: "hi" }),
      ],
      "duration",
    );
    // Last event has no successor gap → content-size estimate (user "hi" → 42).
    expect(
      spans.map((span) => ({ id: span.id, start: span.start, end: span.end })),
    ).toEqual([
      { id: "a", start: 0, end: 500 },
      { id: "t", start: 500, end: 1000 },
      { id: "u", start: 1000, end: 1042 },
    ]);
  });

  it("ignores sub-50ms timestamp gaps and estimates instead", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({
          event_id: "a",
          kind: "assistant",
          ts: 1,
          summary: "x".repeat(100),
        }),
        event({ event_id: "t", kind: "tool", ts: 1.01, summary: "tool" }),
      ],
      "duration",
    );
    // 10ms gap is below the floor → estimate, not 10.
    expect(spans[0]!.end - spans[0]!.start).toBeGreaterThan(10);
    expect(spans[0]!.end - spans[0]!.start).toBe(120 + 100 * 2);
  });

  it("estimates duration when timestamps are equal so Duration differs from sequence", () => {
    const events = [
      event({ event_id: "u", kind: "user", ts: 100, summary: "hi" }),
      event({
        event_id: "a",
        kind: "assistant",
        ts: 100,
        summary: "x".repeat(200),
      }),
      event({
        event_id: "t",
        kind: "tool",
        ts: 100,
        summary: "tool",
        payload: { name: "read", result: "y".repeat(50) },
      }),
    ];
    const sequence = deriveSwimlaneSpans(events, "sequence");
    const duration = deriveSwimlaneSpans(events, "duration");
    expect(sequence.map((s) => s.end - s.start)).toEqual([1, 1, 1]);
    expect(duration[1]!.end - duration[1]!.start).toBeGreaterThan(
      duration[0]!.end - duration[0]!.start,
    );
    expect(duration.map((s) => s.end - s.start)).not.toEqual([1, 1, 1]);
  });

  it("estimates duration from payload bulk when ts and duration fields are missing", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({
          event_id: "u",
          kind: "user",
          ts: 0,
          summary: "hi",
        }),
        event({
          event_id: "a",
          kind: "assistant",
          ts: 0,
          summary: "x".repeat(200),
        }),
        event({
          event_id: "t",
          kind: "tool",
          ts: 0,
          summary: "tool",
          payload: { name: "read", result: "y".repeat(50) },
        }),
      ],
      "duration",
    );
    expect(spans[0]!.end - spans[0]!.start).toBeLessThan(
      spans[1]!.end - spans[1]!.start,
    );
    expect(spans[2]!.end - spans[2]!.start).toBeGreaterThan(
      spans[0]!.end - spans[0]!.start,
    );
    const equal = deriveSwimlaneSpans(
      [
        event({ event_id: "u", kind: "user", ts: 0, summary: "hi" }),
        event({
          event_id: "a",
          kind: "assistant",
          ts: 0,
          summary: "x".repeat(200),
        }),
        event({
          event_id: "t",
          kind: "tool",
          ts: 0,
          summary: "tool",
          payload: { name: "read", result: "y".repeat(50) },
        }),
      ],
      "sequence",
    );
    expect(equal.every((span) => span.end - span.start === 1)).toBe(true);
  });

  it("uses timestamps in actual mode and keeps a visible last span", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({ event_id: "u", kind: "user", ts: 10 }),
        event({ event_id: "a", kind: "assistant", ts: 20 }),
        event({ event_id: "t", kind: "tool", ts: 25 }),
      ],
      "actual",
    );
    expect(
      spans.map((span) => ({
        lane: span.lane,
        start: span.start,
        end: span.end,
      })),
    ).toEqual([
      { lane: "input", start: 10, end: 20 },
      { lane: "model", start: 20, end: 25 },
      { lane: "tools", start: 25, end: 26 },
    ]);
  });
});

describe("trajectory timeline domain helpers", () => {
  it("orderedRange normalizes inverted drags", () => {
    expect(orderedRange(5, 2)).toEqual({ start: 2, end: 5 });
  });

  it("trajectoryFocusEventIds includes spans intersecting the range", () => {
    const spans: SwimlaneSpan[] = [
      {
        id: "a",
        lane: "input",
        kind: "user",
        start: 0,
        end: 1,
        eventIds: ["a"],
        isError: false,
      },
      {
        id: "b",
        lane: "model",
        kind: "assistant",
        start: 1,
        end: 2,
        eventIds: ["b"],
        isError: false,
      },
      {
        id: "c",
        lane: "tools",
        kind: "tool",
        start: 2,
        end: 3,
        eventIds: ["c"],
        isError: false,
      },
    ];
    expect([
      ...trajectoryFocusEventIds(spans, { start: 1.5, end: 2.5 }),
    ]).toEqual(["b", "c"]);
  });

  it("zoomDomain shrinks around the anchor and stays inside the full domain", () => {
    const next = zoomDomain({
      fullStart: 0,
      fullEnd: 100,
      domainStart: 0,
      domainEnd: 100,
      anchorFraction: 0.5,
      zoomFactor: 0.5,
      minDomain: 10,
    });
    expect(next.end - next.start).toBe(50);
    expect(next.start).toBeGreaterThanOrEqual(0);
    expect(next.end).toBeLessThanOrEqual(100);
  });
});
