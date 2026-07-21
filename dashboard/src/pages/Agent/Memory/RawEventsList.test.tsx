/**
 * RawEventsList.test.tsx — L0 raw-events list view.
 *
 * Covers:
 *   - mount → listRawEvents with default pagination; rows render content + type
 *   - event_type filter re-queries with the selected type
 *   - clicking a row opens the detail drawer
 *   - empty (no filter) falls through to the pipeline guided-empty (stats call)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listRawEvents: vi.fn(),
    statsCounts: vi.fn(),
  },
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import RawEventsList from "./RawEventsList";

const api = vi.mocked(memoryDashboardApi, true);

function rawResp(items: unknown[]) {
  return { items, total: items.length, has_more: false } as never;
}

function makeRaw(overrides: Record<string, unknown> = {}) {
  return {
    id: "r1",
    host: "octop",
    session_id: "s1",
    thread_id: "t1",
    user: "u",
    timestamp: new Date("2026-07-15T02:00:00Z").toISOString(),
    event_type: "user_message",
    content: "项目截止日期是周五",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<RawEventsList />", () => {
  it("loads raw events and renders content + type tag", async () => {
    api.listRawEvents.mockResolvedValue(rawResp([makeRaw()]));

    render(<RawEventsList agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("项目截止日期是周五")).toBeInTheDocument();
    });
    expect(api.listRawEvents).toHaveBeenCalledWith("ZYWZTD", {
      offset: 0,
      limit: 20,
    });
    // type tag rendered (user message)
    expect(screen.getAllByText("用户消息").length).toBeGreaterThanOrEqual(1);
  });

  it("re-queries with event_type when the filter changes", async () => {
    api.listRawEvents.mockResolvedValue(rawResp([makeRaw()]));
    const user = userEvent.setup();

    render(<RawEventsList agentId="ZYWZTD" />);
    await waitFor(() => expect(api.listRawEvents).toHaveBeenCalledTimes(1));

    // Open the antd Select and pick "AI 回复".
    await user.click(screen.getByRole("combobox"));
    const option = await screen.findByText("AI 回复");
    await user.click(option);

    await waitFor(() => {
      const calls = api.listRawEvents.mock.calls;
      expect(
        calls.some(
          ([, body]) =>
            (body as { event_type?: string })?.event_type ===
            "assistant_message",
        ),
      ).toBe(true);
    });
  });

  it("opens the detail drawer with full content on row click", async () => {
    api.listRawEvents.mockResolvedValue(
      rawResp([makeRaw({ content: "帮我查一下明天的天气" })]),
    );
    const user = userEvent.setup();

    render(<RawEventsList agentId="ZYWZTD" />);
    await waitFor(() => {
      expect(screen.getByText("帮我查一下明天的天气")).toBeInTheDocument();
    });
    await user.click(screen.getByText("帮我查一下明天的天气"));

    await waitFor(() => {
      expect(screen.getByText("内容")).toBeInTheDocument();
    });
  });

  it("shows the pipeline guided-empty when there are no items", async () => {
    api.listRawEvents.mockResolvedValue(rawResp([]));
    api.statsCounts.mockResolvedValue({ raw_events: 0 } as never);

    render(<RawEventsList agentId="ZYWZTD" />);
    await waitFor(() => expect(api.listRawEvents).toHaveBeenCalled());
    // MemoryPipelineEmpty consults statsCounts to decide its copy.
    await waitFor(() => expect(api.statsCounts).toHaveBeenCalledWith("ZYWZTD"));
  });
});
