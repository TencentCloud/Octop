import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import {
  statsAtomKindsFixture,
  statsCountsFixture,
  statsGrowthFixture,
} from "../../../test/memoryFixtures";

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 600, height: 240 }}>{children}</div>
    ),
  };
});

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    statsCounts: vi.fn(),
    statsAtomKinds: vi.fn(),
    statsGrowth: vi.fn(),
    getExtractConfig: vi.fn(),
  },
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import Overview from "./Overview";

const api = vi.mocked(memoryDashboardApi, true);

const memoryConfig = {
  memory_enabled: true,
  extract_on_session_end: true,
  extract_trigger_mode: "idle" as const,
  extract_idle_seconds: 300,
  extract_interval_seconds: 21600,
};

function stubOverview() {
  api.statsCounts.mockResolvedValue(statsCountsFixture());
  api.statsAtomKinds.mockResolvedValue(statsAtomKindsFixture());
  api.statsGrowth.mockResolvedValue(statsGrowthFixture());
  api.getExtractConfig.mockResolvedValue(memoryConfig);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<Overview />", () => {
  it("renders a compact status, metrics, pipeline, and two charts", async () => {
    stubOverview();
    render(<Overview agentId="ZYWZTD" />);

    await screen.findByText("记忆概览");
    expect(screen.getByText("记忆运行中")).toBeInTheDocument();
    expect(screen.getAllByText("长期记忆").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("关键主题")).toBeInTheDocument();
    expect(screen.getByText("记忆处理进度")).toBeInTheDocument();
    expect(screen.getByText("近 7 天记忆增长")).toBeInTheDocument();
    expect(screen.getByText("记忆类型")).toBeInTheDocument();

    expect(api.statsGrowth).toHaveBeenCalledWith("ZYWZTD", 7);
    expect(api.getExtractConfig).toHaveBeenCalledWith("ZYWZTD");
  });

  it("shows the disabled memory state", async () => {
    stubOverview();
    api.getExtractConfig.mockResolvedValue({
      ...memoryConfig,
      memory_enabled: false,
    });
    render(<Overview agentId="ZYWZTD" />);
    expect(await screen.findByText("记忆已关闭")).toBeInTheDocument();
  });

  it("keeps memory enabled for responses from an older API process", async () => {
    stubOverview();
    const { memory_enabled: _legacyMissingField, ...legacyConfig } =
      memoryConfig;
    api.getExtractConfig.mockResolvedValue(legacyConfig);
    render(<Overview agentId="ZYWZTD" />);
    expect(await screen.findByText("记忆运行中")).toBeInTheDocument();
  });

  it("supports pipeline and settings navigation", async () => {
    stubOverview();
    const onViewConversations = vi.fn();
    const onReviewCandidates = vi.fn();
    const onOpenSettings = vi.fn();
    render(
      <Overview
        agentId="ZYWZTD"
        onViewConversations={onViewConversations}
        onReviewCandidates={onReviewCandidates}
        onOpenSettings={onOpenSettings}
      />,
    );

    await screen.findByText("记忆处理进度");
    fireEvent.click(screen.getByRole("button", { name: /对话记忆/ }));
    fireEvent.click(screen.getByRole("button", { name: /待处理/ }));
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    expect(onViewConversations).toHaveBeenCalledOnce();
    expect(onReviewCandidates).toHaveBeenCalledOnce();
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });

  it("isolates partial endpoint failures", async () => {
    api.statsCounts.mockRejectedValue(new Error("counts"));
    api.statsAtomKinds.mockRejectedValue(new Error("kinds"));
    api.statsGrowth.mockRejectedValue(new Error("growth"));
    api.getExtractConfig.mockRejectedValue(new Error("config"));
    render(<Overview agentId="ZYWZTD" />);

    await screen.findByText("记忆概览");
    expect(screen.getByText("暂无记忆类型数据")).toBeInTheDocument();
    expect(screen.getByText("近 7 天暂无新增")).toBeInTheDocument();
  });

  it("refreshes all overview sources", async () => {
    stubOverview();
    render(<Overview agentId="ZYWZTD" />);
    await waitFor(() => expect(api.statsCounts).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() => expect(api.statsCounts).toHaveBeenCalledTimes(2));
    expect(api.getExtractConfig).toHaveBeenCalledTimes(2);
  });
});
