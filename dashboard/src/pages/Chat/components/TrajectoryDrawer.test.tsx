import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";

const { session, useTrajectorySession, messageError } = vi.hoisted(() => {
  const session = {
    events: [] as TrajectoryEvent[],
    metrics: null,
    loading: false,
    error: false,
    hasMore: false,
    retry: vi.fn(),
    loadEarlier: vi.fn(async () => {}),
    refresh: vi.fn(),
  };
  return {
    session,
    useTrajectorySession: vi.fn(() => session),
    messageError: vi.fn(),
  };
});

const exportMock = vi.fn();

vi.mock("../hooks/useTrajectorySession", () => ({
  useTrajectorySession: (...args: unknown[]) => useTrajectorySession(...args),
}));

vi.mock("../../../hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: (...args: unknown[]) => messageError(...args) },
}));

vi.mock("../../../api/modules/trajectory", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/trajectory")
  >();
  return {
    ...actual,
    trajectoryApi: {
      ...actual.trajectoryApi,
      export: (...args: unknown[]) => exportMock(...args),
    },
  };
});

import TrajectoryDrawer from "./TrajectoryDrawer";

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
    payload: { name: "read_file", args: { path: "a.py" }, result: "ok" },
  }),
  event({
    event_id: "t2",
    kind: "tool",
    seq: 4,
    turn_id: "turn-b",
    summary: "save a.py",
    payload: { name: "write_file", args: { path: "a.py" }, result: "saved" },
  }),
];

async function renderDrawer(ui: ReactElement) {
  const view = render(ui);
  await act(async () => {
    await Promise.resolve();
  });
  return view;
}

describe("TrajectoryDrawer", () => {
  beforeEach(() => {
    session.events = sampleEvents;
    session.loading = false;
    session.error = false;
    session.hasMore = false;
    session.retry.mockReset();
    session.loadEarlier.mockReset();
    session.refresh.mockReset();
    useTrajectorySession.mockClear();
    exportMock.mockReset();
    messageError.mockReset();
  });

  it("renders the drawer title, Duration toggle, and timeline when open", async () => {
    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    expect(useTrajectorySession).toHaveBeenCalledWith({
      agentId: "A1",
      threadId: "T1",
      visible: true,
    });
    expect(screen.getByText("Trajectory")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Duration" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Trajectory timeline" }),
    ).toBeInTheDocument();
  });

  it("dims ledger search misses and collapses turns or consecutive calls", async () => {
    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("Request #1")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "read_file" },
    });
    const readRow = screen
      .getAllByText("read_file")
      .map((node) => node.closest("tr"))
      .find((node): node is HTMLTableRowElement => node != null);
    const writeRow = screen
      .getAllByText("write_file")
      .map((node) => node.closest("tr"))
      .find((node): node is HTMLTableRowElement => node != null);
    expect(readRow).toHaveAttribute("data-search-match", "true");
    expect(writeRow).toHaveAttribute("data-search-match", "false");

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Turns" }));
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByText("Request #1")).not.toBeInTheDocument();
    expect(screen.queryByText("read_file")).not.toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Turns" }));
    fireEvent.click(screen.getByRole("button", { name: "Calls" }));
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("Request #1")).toBeInTheDocument();
    expect(document.querySelectorAll('tr[data-kind="tool"]')).toHaveLength(0);
    expect(
      document.querySelectorAll('tr[data-kind="collapsed-summary"]'),
    ).toHaveLength(1);
    expect(
      screen.getByText(/2 tool calls · read_file, write_file/),
    ).toBeInTheDocument();
  });

  it("dims timeline search hits from the full event list while calls are collapsed", async () => {
    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Calls" }));
    expect(document.querySelectorAll('tr[data-kind="tool"]')).toHaveLength(0);

    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "read_file" },
    });

    expect(document.querySelector('[data-event-ids="t1"]')).toHaveAttribute(
      "data-search-match",
      "true",
    );
    expect(document.querySelector('[data-event-ids="u1"]')).toHaveAttribute(
      "data-search-match",
      "false",
    );
  });

  it("keeps the inspector visible and shows a placeholder until a record is selected", async () => {
    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    expect(screen.getByTestId("trajectory-inspector-pane")).toBeInTheDocument();
    expect(screen.getByText("Select a record")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /hello/ }));
    expect(screen.queryByText("Select a record")).not.toBeInTheDocument();
    expect(screen.getByText("Kind")).toBeInTheDocument();
  });

  it("switches timeline duration mode from the toolbar", async () => {
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
    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    expect(screen.getByRole("button", { name: /Model/ })).toHaveAttribute(
      "data-end",
      "1",
    );

    fireEvent.click(screen.getByRole("button", { name: "Duration" }));
    expect(screen.getByRole("button", { name: /Model/ })).toHaveAttribute(
      "data-end",
      "100",
    );
    expect(screen.getByRole("button", { name: /Tools/ })).toHaveAttribute(
      "data-end",
      "150",
    );
  });

  it("wires loadEarlier to the timeline earlier-history control", async () => {
    session.hasMore = true;
    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Load earlier history" }),
      );
    });
    expect(session.loadEarlier).toHaveBeenCalled();
  });

  it("exports from the drawer header only", async () => {
    const blob = new Blob(["{}\n"], { type: "application/x-ndjson" });
    exportMock.mockResolvedValue(blob);
    const createObjectURL = vi.fn(() => "blob:trajectory-export");
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    expect(screen.getAllByRole("button", { name: "Export" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => {
      expect(exportMock).toHaveBeenCalledWith("A1", "T1");
      expect(createObjectURL).toHaveBeenCalledWith(blob);
      expect(click).toHaveBeenCalled();
    });
    expect(messageError).not.toHaveBeenCalled();
  });

  it("toasts when export fails", async () => {
    exportMock.mockRejectedValue(new Error("export failed"));

    await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => {
      expect(messageError).toHaveBeenCalledWith("Failed to export trajectory");
    });
  });

  it("shows empty, loading, and error+retry inside the body", async () => {
    session.events = [];
    const view = await renderDrawer(
      <TrajectoryDrawer agentId="A1" threadId={null} open onClose={() => {}} />,
    );
    expect(
      screen.getByText("Select a session to view trajectory"),
    ).toBeInTheDocument();

    session.loading = true;
    view.rerender(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(document.querySelector(".ant-spin")).not.toBeNull();

    session.loading = false;
    session.error = true;
    view.rerender(
      <TrajectoryDrawer agentId="A1" threadId="T1" open onClose={() => {}} />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Failed to load trajectory")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(session.retry).toHaveBeenCalled();
  });
});
