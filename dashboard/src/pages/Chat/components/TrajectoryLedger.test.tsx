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
            payload: { name: "read_file" },
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
    expect(kept.closest("li")).toHaveAttribute("data-focus-match", "true");
    expect(dimmed.closest("li")).toHaveAttribute("data-focus-match", "false");
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
    expect(headers[0]).toHaveTextContent("turn-a");
    expect(headers[1]).toHaveTextContent("turn-b");
  });
});
