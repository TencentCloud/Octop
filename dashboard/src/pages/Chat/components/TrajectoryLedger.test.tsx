import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
      />,
    );

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("Request #3")).toBeInTheDocument();
  });
});
