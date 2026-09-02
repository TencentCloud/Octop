import { act, fireEvent, render, screen } from "@testing-library/react";
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

function mockTrack(track: HTMLElement): HTMLElement {
  vi.spyOn(track, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 400,
    bottom: 50,
    width: 400,
    height: 50,
    toJSON: () => ({}),
  });
  return track;
}

function pointer(
  target: HTMLElement,
  type: "pointerdown" | "pointermove" | "pointerup",
  init: { button?: number; pointerId?: number; clientX: number },
) {
  const event = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    button: init.button ?? 0,
    buttons: (init.button ?? 0) === 0 ? 1 : 0,
    clientX: init.clientX,
    clientY: 10,
  });
  Object.defineProperty(event, "pointerId", {
    value: init.pointerId ?? 1,
  });
  Object.defineProperty(event, "pointerType", { value: "mouse" });
  act(() => {
    target.dispatchEvent(event);
  });
}

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

  it("commits a range when dragging on the track", () => {
    const onRangeChange = vi.fn();
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        range={null}
        onRangeChange={onRangeChange}
        selectedEventId={null}
        searchMatchIds={null}
        onRecordSelect={() => {}}
      />,
    );
    const track = mockTrack(
      screen.getByRole("group", { name: "Trajectory timeline" }),
    );
    pointer(track, "pointerdown", { clientX: 40 });
    pointer(track, "pointermove", { clientX: 200 });
    pointer(track, "pointerup", { clientX: 200 });
    expect(onRangeChange).toHaveBeenCalledTimes(1);
    const committed = onRangeChange.mock.calls[0][0] as {
      start: number;
      end: number;
    };
    expect(committed.end).toBeGreaterThan(committed.start);
  });

  it("clears the range on Escape", () => {
    const onRangeChange = vi.fn();
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        range={{ start: 0, end: 2 }}
        onRangeChange={onRangeChange}
        selectedEventId={null}
        searchMatchIds={null}
        onRecordSelect={() => {}}
      />,
    );
    fireEvent.keyDown(
      screen.getByRole("group", { name: "Trajectory timeline" }),
      { key: "Escape" },
    );
    expect(onRangeChange).toHaveBeenCalledWith(null);
  });

  it("calls onRecordSelect after a whitespace range commit", async () => {
    const onRangeChange = vi.fn();
    const onRecordSelect = vi.fn();
    render(
      <TrajectoryTimeline
        events={sampleEvents}
        mode="sequence"
        range={null}
        onRangeChange={onRangeChange}
        selectedEventId={null}
        searchMatchIds={null}
        onRecordSelect={onRecordSelect}
      />,
    );
    const track = mockTrack(
      screen.getByRole("group", { name: "Trajectory timeline" }),
    );
    pointer(track, "pointerdown", { clientX: 10 });
    pointer(track, "pointerup", { clientX: 10 });
    expect(onRangeChange).toHaveBeenCalledTimes(1);
    expect(onRangeChange.mock.calls[0][0]).not.toBeNull();

    await Promise.resolve();
    fireEvent.click(screen.getByRole("button", { name: /Input: user/ }));
    expect(onRecordSelect).toHaveBeenCalledWith("u");
  });
});
