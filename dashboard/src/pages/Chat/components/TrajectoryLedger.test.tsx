import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import TrajectoryLedger from "./TrajectoryLedger";

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

const idle = {
  selectedEventId: null as string | null,
  onSelect: () => {},
  focusEventIds: null as ReadonlySet<string> | null,
  searchMatchIds: null as ReadonlySet<string> | null,
};

describe("TrajectoryLedger", () => {
  it("renders tool names and assistant Request # labels", () => {
    render(
      <TrajectoryLedger
        events={[
          event({
            event_id: "tool-1",
            kind: "tool",
            seq: 1,
            summary: "tool read_file",
            payload: {
              name: "read_file",
              args: { path: "a.py" },
              result: "ok",
            },
          }),
          event({
            event_id: "asst-1",
            kind: "assistant",
            seq: 2,
            request_seq: 3,
            summary: "thinking…",
          }),
        ]}
        {...idle}
      />,
    );

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("Request #3")).toBeInTheDocument();
    expect(screen.getByText("TOOL")).toBeInTheDocument();
    expect(screen.getByText("ASSISTANT")).toBeInTheDocument();
  });

  it("calls onSelect when a row is clicked and does not expand Raw inline", () => {
    const onSelect = vi.fn();
    render(
      <TrajectoryLedger
        events={[
          event({
            event_id: "user-1",
            kind: "user",
            summary: "hello there",
            payload: {},
          }),
        ]}
        {...idle}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /hello there/ }));
    expect(onSelect).toHaveBeenCalledWith("user-1");
    expect(screen.queryByTestId("trajectory-payload")).not.toBeInTheDocument();
  });

  it("marks the selected row and dims rows outside the focus set", () => {
    render(
      <TrajectoryLedger
        events={[
          event({
            event_id: "in",
            kind: "user",
            summary: "kept",
          }),
          event({
            event_id: "out",
            kind: "user",
            summary: "dimmed",
          }),
        ]}
        {...idle}
        selectedEventId="in"
        focusEventIds={new Set(["in"])}
      />,
    );

    const kept = screen.getByRole("button", { name: /kept/ });
    const dimmed = screen.getByRole("button", { name: /dimmed/ });
    expect(kept).toHaveAttribute("aria-selected", "true");
    expect(dimmed).toHaveAttribute("aria-selected", "false");
    expect(kept).toHaveAttribute("data-focus-match", "true");
    expect(dimmed).toHaveAttribute("data-focus-match", "false");
  });

  it("scrolls the selected row into view", () => {
    const scrollIntoView = vi.fn();
    const proto = Element.prototype as Element & {
      scrollIntoView: typeof scrollIntoView;
    };
    const original = proto.scrollIntoView;
    proto.scrollIntoView = scrollIntoView;

    try {
      const { rerender } = render(
        <TrajectoryLedger
          events={[
            event({
              event_id: "first",
              kind: "user",
              summary: "kept",
            }),
            event({
              event_id: "second",
              kind: "assistant",
              summary: "later",
            }),
          ]}
          {...idle}
        />,
      );

      expect(scrollIntoView).not.toHaveBeenCalled();

      rerender(
        <TrajectoryLedger
          events={[
            event({
              event_id: "first",
              kind: "user",
              summary: "kept",
            }),
            event({
              event_id: "second",
              kind: "assistant",
              summary: "later",
            }),
          ]}
          {...idle}
          selectedEventId="second"
        />,
      );

      expect(scrollIntoView).toHaveBeenCalled();
    } finally {
      proto.scrollIntoView = original;
    }
  });

  it("inserts a turn header when turn_id changes", () => {
    render(
      <TrajectoryLedger
        events={[
          event({
            event_id: "a",
            kind: "user",
            turn_id: "turn-a",
            summary: "first",
          }),
          event({
            event_id: "b",
            kind: "assistant",
            turn_id: "turn-a",
            summary: "same turn",
          }),
          event({
            event_id: "c",
            kind: "user",
            turn_id: "turn-b",
            summary: "next turn",
          }),
        ]}
        {...idle}
      />,
    );

    const headers = screen.getAllByTestId("trajectory-turn-header");
    expect(headers).toHaveLength(2);
    expect(headers[0]).toHaveTextContent("T1");
    expect(headers[1]).toHaveTextContent("T2");
  });

  it("follows the live tail when near the bottom", () => {
    const { rerender } = render(
      <TrajectoryLedger
        events={[
          event({ event_id: "e1", kind: "user", seq: 1, summary: "one" }),
        ]}
        {...idle}
      />,
    );

    const pane = screen.getByTestId("trajectory-ledger-pane");
    Object.defineProperty(pane, "clientHeight", {
      configurable: true,
      value: 100,
    });
    Object.defineProperty(pane, "scrollHeight", {
      configurable: true,
      get() {
        return 400;
      },
    });
    let scrollTop = 0;
    Object.defineProperty(pane, "scrollTop", {
      configurable: true,
      get() {
        return scrollTop;
      },
      set(value: number) {
        scrollTop = value;
      },
    });

    rerender(
      <TrajectoryLedger
        events={[
          event({ event_id: "e1", kind: "user", seq: 1, summary: "one" }),
          event({ event_id: "e2", kind: "assistant", seq: 2, summary: "two" }),
        ]}
        {...idle}
      />,
    );

    expect(scrollTop).toBe(400);
  });

  it("does not follow the live tail after the user scrolls up", () => {
    const { rerender } = render(
      <TrajectoryLedger
        events={[
          event({ event_id: "e1", kind: "user", seq: 1, summary: "one" }),
          event({ event_id: "e2", kind: "assistant", seq: 2, summary: "two" }),
        ]}
        {...idle}
      />,
    );

    const pane = screen.getByTestId("trajectory-ledger-pane");
    Object.defineProperty(pane, "clientHeight", {
      configurable: true,
      value: 100,
    });
    Object.defineProperty(pane, "scrollHeight", {
      configurable: true,
      value: 500,
    });
    let scrollTop = 50;
    Object.defineProperty(pane, "scrollTop", {
      configurable: true,
      get() {
        return scrollTop;
      },
      set(value: number) {
        scrollTop = value;
      },
    });

    fireEvent.scroll(pane);
    expect(scrollTop).toBe(50);

    rerender(
      <TrajectoryLedger
        events={[
          event({ event_id: "e1", kind: "user", seq: 1, summary: "one" }),
          event({ event_id: "e2", kind: "assistant", seq: 2, summary: "two" }),
          event({ event_id: "e3", kind: "tool", seq: 3, summary: "three" }),
        ]}
        {...idle}
      />,
    );

    expect(scrollTop).toBe(50);
  });
});
