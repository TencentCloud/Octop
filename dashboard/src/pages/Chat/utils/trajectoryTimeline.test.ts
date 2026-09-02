import { describe, expect, it } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import { deriveSwimlaneSpans } from "./trajectoryTimeline";

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

  it("places events on lanes and merges consecutive same-lane tools in sequence mode", () => {
    const spans = deriveSwimlaneSpans(
      [
        event({ event_id: "u", kind: "user" }),
        event({ event_id: "a", kind: "assistant" }),
        event({ event_id: "t1", kind: "tool" }),
        event({ event_id: "t2", kind: "tool" }),
        event({ event_id: "u2", kind: "user" }),
      ],
      "sequence",
    );
    expect(
      spans.map((span) => ({
        lane: span.lane,
        eventIds: span.eventIds,
        start: span.start,
        end: span.end,
      })),
    ).toEqual([
      { lane: "input", eventIds: ["u"], start: 0, end: 1 },
      { lane: "model", eventIds: ["a"], start: 1, end: 2 },
      { lane: "tools", eventIds: ["t1", "t2"], start: 2, end: 4 },
      { lane: "input", eventIds: ["u2"], start: 4, end: 5 },
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
