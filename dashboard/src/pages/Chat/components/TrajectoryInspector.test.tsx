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

import TrajectoryInspector from "./TrajectoryInspector";

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

describe("TrajectoryInspector", () => {
  beforeEach(() => {
    eventMock.mockReset();
  });

  it("shows a placeholder when no event is selected", () => {
    render(<TrajectoryInspector agentId="A1" threadId="T1" event={null} />);
    expect(screen.getByText("Select a record")).toBeInTheDocument();
  });

  it("shows Summary fields for a selected event", () => {
    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={event({
          event_id: "asst-1",
          kind: "assistant",
          request_seq: 3,
          is_error: false,
          summary: "thinking…",
          payload: {
            llm_duration_ms: 120,
            ttft_ms: 40,
            input_tokens: 10,
            output_tokens: 20,
          },
        })}
      />,
    );

    expect(screen.getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText("assistant")).toBeInTheDocument();
    expect(screen.getByText(/Request #3/)).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("loads event detail on the Raw tab", async () => {
    eventMock.mockResolvedValue(
      event({
        event_id: "user-1",
        kind: "user",
        summary: "hello there",
        payload: { content: "hello there" },
      }),
    );

    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={event({
          event_id: "user-1",
          kind: "user",
          summary: "hello there",
          payload: {},
        })}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Raw" }));

    await waitFor(() => {
      expect(eventMock).toHaveBeenCalledWith("A1", "T1", "user-1");
      expect(screen.getByTestId("trajectory-raw")).toHaveTextContent(
        '"content": "hello there"',
      );
    });
  });
});
