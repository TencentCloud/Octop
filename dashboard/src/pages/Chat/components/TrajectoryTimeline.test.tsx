import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import TrajectoryTimeline from "./TrajectoryTimeline";

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

const sampleEvents: TrajectoryEvent[] = [
  event({ event_id: "u", kind: "user", seq: 1 }),
  event({
    event_id: "a",
    kind: "assistant",
    seq: 2,
    request_seq: 1,
    payload: { llm_duration_ms: 100 },
  }),
  event({
    event_id: "t1",
    kind: "tool",
    seq: 3,
    payload: { name: "read_file", tool_duration_ms: 50 },
  }),
  event({
    event_id: "t2",
    kind: "tool",
    seq: 4,
    payload: { name: "write_file", tool_duration_ms: 50 },
  }),
];

describe("TrajectoryTimeline", () => {
  it("renders a keyboard-focusable span on each lane and merges consecutive tools", () => {
    render(<TrajectoryTimeline events={sampleEvents} mode="sequence" />);

    expect(
      screen.getByRole("group", { name: "Trajectory timeline" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Tools")).toBeInTheDocument();

    const spans = screen.getAllByRole("button");
    expect(spans).toHaveLength(3);
    expect(spans[0]).toHaveAttribute("data-lane", "input");
    expect(spans[1]).toHaveAttribute("data-lane", "model");
    expect(spans[2]).toHaveAttribute("data-lane", "tools");
    expect(spans[2]).toHaveAttribute("data-event-ids", "t1,t2");
    spans.forEach((span) => {
      expect(span).toHaveAttribute("type", "button");
    });
    spans[0].focus();
    expect(spans[0]).toHaveFocus();
  });

  it("sizes duration-mode spans from payload durations", () => {
    render(
      <TrajectoryTimeline events={sampleEvents.slice(1)} mode="duration" />,
    );

    const model = screen.getByRole("button", { name: /Model/ });
    const tools = screen.getByRole("button", { name: /Tools/ });
    expect(model).toHaveAttribute("data-start", "0");
    expect(model).toHaveAttribute("data-end", "100");
    expect(tools).toHaveAttribute("data-start", "100");
    expect(tools).toHaveAttribute("data-end", "200");
  });

  it("toggles focus when a span is activated", () => {
    const onFocusSpan = vi.fn();
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        onFocusSpan={onFocusSpan}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Tools/ }));
    expect(onFocusSpan).toHaveBeenCalledTimes(1);
    const span = onFocusSpan.mock.calls[0][0] as { eventIds: string[] };
    expect(span.eventIds).toEqual(["t1", "t2"]);
  });
});
