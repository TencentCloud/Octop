import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";

const eventMock = vi.fn();

vi.mock("../../../api/modules/trajectory", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/trajectory")
  >();
  return {
    ...actual,
    trajectoryApi: {
      ...actual.trajectoryApi,
      event: (...args: unknown[]) => eventMock(...args),
    },
  };
});

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
  beforeEach(() => {
    eventMock.mockReset();
  });

  it("renders tool names and assistant Request # labels", () => {
    render(
      <TrajectoryLedger
        agentId="A1"
        threadId="T1"
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

  it("fetches event detail and shows the expanded payload on row click", async () => {
    eventMock.mockResolvedValue(
      event({
        event_id: "user-1",
        kind: "user",
        summary: "hello there",
        payload: { content: "hello there" },
      }),
    );

    render(
      <TrajectoryLedger
        agentId="A1"
        threadId="T1"
        events={[
          event({
            event_id: "user-1",
            kind: "user",
            summary: "hello there",
            payload: {},
          }),
        ]}
      />,
    );

    expect(screen.queryByTestId("trajectory-payload")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /hello there/ }));

    await waitFor(() => {
      expect(eventMock).toHaveBeenCalledWith("A1", "T1", "user-1");
      expect(screen.getByTestId("trajectory-payload")).toHaveTextContent(
        '"content": "hello there"',
      );
    });
  });
});
