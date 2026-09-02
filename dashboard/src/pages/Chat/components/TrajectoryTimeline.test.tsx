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

const interactiveProps = {
  range: null,
  onRangeChange: () => {},
  selectedEventId: null,
  searchMatchIds: null,
  onRecordSelect: () => {},
} as const;

describe("TrajectoryTimeline", () => {
  it("renders discrete per-event spans on a shared three-lane track", () => {
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        {...interactiveProps}
      />,
    );

    expect(
      screen.getByRole("group", { name: "Trajectory timeline" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Tools")).toBeInTheDocument();

    const spans = screen.getAllByRole("button", {
      name: /^(Input|Model|Tools):/,
    });
    expect(spans).toHaveLength(4);
    expect(spans[0]).toHaveAttribute("data-lane", "input");
    expect(spans[0]).toHaveAttribute("data-timeline-span", "user");
    expect(spans[1]).toHaveAttribute("data-lane", "model");
    expect(spans[1]).toHaveAttribute("data-timeline-span", "message");
    expect(spans[2]).toHaveAttribute("data-lane", "tools");
    expect(spans[2]).toHaveAttribute("data-event-ids", "t1");
    expect(spans[3]).toHaveAttribute("data-event-ids", "t2");
    spans[0].focus();
    expect(spans[0]).toHaveFocus();
  });

  it("sizes duration-mode spans from payload durations", () => {
    render(
      <TrajectoryTimeline
        events={sampleEvents.slice(1)}
        mode="duration"
        {...interactiveProps}
      />,
    );

    const model = screen.getByRole("button", { name: /Model: assistant/ });
    const tools = screen.getAllByRole("button", { name: /Tools: tool/ });
    expect(model).toHaveAttribute("data-start", "0");
    expect(model).toHaveAttribute("data-end", "100");
    expect(tools[0]).toHaveAttribute("data-start", "100");
    expect(tools[0]).toHaveAttribute("data-end", "150");
    expect(tools[1]).toHaveAttribute("data-start", "150");
    expect(tools[1]).toHaveAttribute("data-end", "200");
  });

  it("calls onRecordSelect when a span is clicked", () => {
    const onRecordSelect = vi.fn();
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        range={null}
        onRangeChange={() => {}}
        selectedEventId={null}
        searchMatchIds={null}
        onRecordSelect={onRecordSelect}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Input: user/ }));
    expect(onRecordSelect).toHaveBeenCalledWith("u");
  });

  it("dims non-matching spans when searchMatchIds is set", () => {
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        range={null}
        onRangeChange={() => {}}
        selectedEventId={null}
        searchMatchIds={new Set(["u"])}
        onRecordSelect={() => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Model: assistant/ }),
    ).toHaveAttribute("data-search-match", "false");
    expect(screen.getByRole("button", { name: /Input: user/ })).toHaveAttribute(
      "data-search-match",
      "true",
    );
  });
});
