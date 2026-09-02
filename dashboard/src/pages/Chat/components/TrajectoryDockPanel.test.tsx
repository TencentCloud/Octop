import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";

const { session } = vi.hoisted(() => ({
  session: {
    events: [] as TrajectoryEvent[],
    loading: false,
    error: false,
    retry: vi.fn(),
  },
}));

vi.mock("../hooks/useTrajectorySession", () => ({
  useTrajectorySession: () => session,
}));

vi.mock("../../../api/modules/trajectory", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/trajectory")
  >();
  return {
    ...actual,
    trajectoryApi: {
      ...actual.trajectoryApi,
      metrics: vi.fn().mockResolvedValue({
        turns: 0,
        steps: 0,
        llm_duration_ms: null,
        tool_duration_ms: null,
        ttft_avg_ms: null,
        tok_per_s: null,
        cache_hit_ratio: null,
        input_tokens: null,
        output_tokens: null,
        cache_read_tokens: null,
      }),
      export: vi.fn(),
    },
  };
});

import TrajectoryDockPanel from "./TrajectoryDockPanel";

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
  event({
    event_id: "u1",
    kind: "user",
    seq: 1,
    turn_id: "turn-a",
    summary: "hello",
  }),
  event({
    event_id: "a1",
    kind: "assistant",
    seq: 2,
    turn_id: "turn-a",
    request_seq: 1,
    summary: "thinking",
  }),
  event({
    event_id: "t1",
    kind: "tool",
    seq: 3,
    turn_id: "turn-a",
    summary: "open a.py",
    payload: { name: "read_file" },
  }),
  event({
    event_id: "t2",
    kind: "tool",
    seq: 4,
    turn_id: "turn-b",
    summary: "save a.py",
    payload: { name: "write_file" },
  }),
];

async function renderDock(ui: ReactElement) {
  const view = render(ui);
  await act(async () => {
    await Promise.resolve();
  });
  return view;
}

describe("TrajectoryDockPanel toolbar", () => {
  it("filters the ledger by search and collapses turns or consecutive calls", async () => {
    session.events = sampleEvents;
    await renderDock(<TrajectoryDockPanel agentId="A1" threadId="T1" />);

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("Request #1")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "read_file" },
    });
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("write_file")).not.toBeInTheDocument();
    expect(screen.queryByText("Request #1")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Collapse turns" }));
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByText("Request #1")).not.toBeInTheDocument();
    expect(screen.queryByText("read_file")).not.toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse turns" }));
    fireEvent.click(screen.getByRole("button", { name: "Collapse calls" }));
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("Request #1")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("write_file")).not.toBeInTheDocument();
  });

  it("switches swimlane duration mode from the toolbar", async () => {
    session.events = [
      event({
        event_id: "a",
        kind: "assistant",
        payload: { llm_duration_ms: 100 },
      }),
      event({
        event_id: "t",
        kind: "tool",
        payload: { name: "read_file", tool_duration_ms: 50 },
      }),
    ];
    await renderDock(<TrajectoryDockPanel agentId="A1" threadId="T1" />);

    const mode = screen.getByRole("combobox", { name: "Time scale" });
    expect(screen.getByRole("button", { name: /Model/ })).toHaveAttribute(
      "data-end",
      "1",
    );

    fireEvent.change(mode, { target: { value: "duration" } });
    expect(screen.getByRole("button", { name: /Model/ })).toHaveAttribute(
      "data-end",
      "100",
    );
    expect(screen.getByRole("button", { name: /Tools/ })).toHaveAttribute(
      "data-end",
      "150",
    );
  });
});
