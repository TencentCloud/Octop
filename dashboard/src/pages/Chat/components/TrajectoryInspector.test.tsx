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

import TrajectoryInspector, { findSourceEventId } from "./TrajectoryInspector";

function event(
  overrides: Partial<TrajectoryEvent> &
    Pick<TrajectoryEvent, "event_id" | "kind">,
): TrajectoryEvent {
  return {
    thread_id: "T1",
    agent_id: "A1",
    seq: 1,
    ts: 1_700_000_000,
    turn_id: null,
    request_seq: null,
    is_error: false,
    summary: "",
    payload: {},
    ...overrides,
  };
}

describe("findSourceEventId", () => {
  it("prefers the assistant event for a request_seq", () => {
    const events = [
      event({ event_id: "a", kind: "assistant", request_seq: 3 }),
      event({ event_id: "t", kind: "tool", request_seq: 3 }),
    ];
    expect(findSourceEventId(events, 3, "t")).toBe("a");
  });
});

describe("TrajectoryInspector", () => {
  beforeEach(() => {
    eventMock.mockReset();
  });

  it("shows a placeholder when no event is selected", () => {
    render(<TrajectoryInspector agentId="A1" threadId="T1" event={null} />);
    expect(screen.getByText("Select a record")).toBeInTheDocument();
  });

  it("shows Summary fields and Request Timing for a selected event", () => {
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
            tok_per_s: 12.5,
          },
        })}
      />,
    );

    expect(screen.getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getAllByText("ASSISTANT").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Request #3/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Request Timing")).toBeInTheDocument();
    expect(screen.getAllByText("120ms").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("40ms").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("80ms")).toBeInTheDocument();
    expect(screen.getByText("12.5 tok/s")).toBeInTheDocument();
  });

  it("jumps Source Request # to the parent assistant", () => {
    const onSelectEvent = vi.fn();
    const assistant = event({
      event_id: "asst-1",
      kind: "assistant",
      request_seq: 5,
      summary: "calling tools",
    });
    const tool = event({
      event_id: "tool-1",
      kind: "tool",
      request_seq: 5,
      summary: "read",
      payload: { name: "read" },
    });

    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={tool}
        events={[assistant, tool]}
        onSelectEvent={onSelectEvent}
      />,
    );

    fireEvent.click(screen.getByTestId("trajectory-source-jump"));
    expect(onSelectEvent).toHaveBeenCalledWith("asst-1");
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

  it("loads full content on the Preview tab", async () => {
    eventMock.mockResolvedValue(
      event({
        event_id: "ctx-1",
        kind: "context",
        summary: "clipped…",
        payload: {
          label: "AGENTS.md",
          content:
            "---\nsummary: meta\n---\n\n## Rules\n\nPrefer **BackendWorkspace** paths.",
        },
      }),
    );

    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={event({
          event_id: "ctx-1",
          kind: "context",
          summary: "clipped…",
          payload: { label: "AGENTS.md" },
        })}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));

    await waitFor(() => {
      expect(eventMock).toHaveBeenCalledWith("A1", "T1", "ctx-1");
      const preview = screen.getByTestId("trajectory-preview");
      expect(preview).toHaveTextContent("Prefer BackendWorkspace paths");
      // Rendered markdown — not the raw ## / ** markers.
      expect(preview.querySelector("h2")).toHaveTextContent("Rules");
      expect(preview.querySelector("strong")).toHaveTextContent(
        "BackendWorkspace",
      );
      expect(preview).not.toHaveTextContent("summary: meta");
    });
  });

  it("labels the middle tab Result for tool events", () => {
    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={event({
          event_id: "tool-1",
          kind: "tool",
          summary: "memory_search",
          payload: { name: "memory_search", result: "Memory hits:\n- a" },
        })}
      />,
    );

    expect(screen.getByRole("tab", { name: "Result" })).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Preview" }),
    ).not.toBeInTheDocument();
  });

  it("renders tool Result as plain text, not markdown", async () => {
    eventMock.mockResolvedValue(
      event({
        event_id: "tool-1",
        kind: "tool",
        summary: "read",
        payload: {
          name: "read",
          result: "<path>/tmp/a.rs</path>\n## Heading\n**bold**",
        },
      }),
    );

    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={event({
          event_id: "tool-1",
          kind: "tool",
          summary: "read",
          payload: { name: "read" },
        })}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "Result" }));

    await waitFor(() => {
      const preview = screen.getByTestId("trajectory-preview");
      expect(preview).toHaveTextContent("<path>/tmp/a.rs</path>");
      expect(preview).toHaveTextContent("## Heading");
      expect(preview).toHaveTextContent("**bold**");
      expect(preview.querySelector("h2")).toBeNull();
      expect(preview.querySelector("strong")).toBeNull();
    });
  });

  it("unwraps MCP content blocks on the Result tab and shows Payload", async () => {
    eventMock.mockResolvedValue(
      event({
        event_id: "tool-mcp",
        kind: "tool",
        summary: "tool list_projects",
        payload: {
          name: "list_projects",
          args: {},
          result: [
            {
              type: "text",
              text: '{\n  "id": "1",\n  "name": "工作"\n}',
            },
          ],
        },
      }),
    );

    render(
      <TrajectoryInspector
        agentId="A1"
        threadId="T1"
        event={event({
          event_id: "tool-mcp",
          kind: "tool",
          summary: "tool list_projects",
          payload: {
            name: "list_projects",
            args: {},
            result: [
              {
                type: "text",
                text: '{\n  "id": "1",\n  "name": "工作"\n}',
              },
            ],
          },
        })}
      />,
    );

    expect(screen.getByRole("tab", { name: "Payload" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Result" }));

    await waitFor(() => {
      const preview = screen.getByTestId("trajectory-preview");
      expect(preview).toHaveTextContent('"name": "工作"');
      expect(preview).not.toHaveTextContent("tool list_projects");
      expect(preview).not.toHaveTextContent('"type": "text"');
    });
  });
});
