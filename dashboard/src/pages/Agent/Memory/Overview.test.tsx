/**
 * Overview.test.tsx — overview metrics and insight chart coverage.
 *
 * Coverage:
 *   - stats endpoints fan out in parallel
 *   - overview subtitle and KPI metrics render
 *   - insight charts and composition blocks render
 *   - partial failures are isolated with Promise.allSettled
 *   - empty agentId does not issue requests
 *   - refresh triggers another fan-out
 */

import "@testing-library/jest-dom/vitest";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import {
  makeAtom,
  listAtomsResp,
  statsCountsFixture,
  statsAtomKindsFixture,
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
    listAtoms: vi.fn(),
  },
  isAtomDeprecated: (a: { deprecated_at?: string | null }) =>
    a.deprecated_at != null,
}));

vi.mock("./MigrateMemory", () => ({
  default: () => null,
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import Overview from "./Overview";

const api = vi.mocked(memoryDashboardApi, true);

beforeEach(() => {
  vi.clearAllMocks();
});

function stubStats() {
  api.statsCounts.mockResolvedValue(statsCountsFixture());
  api.statsAtomKinds.mockResolvedValue(statsAtomKindsFixture());
  api.statsGrowth.mockResolvedValue(statsGrowthFixture());
  api.listAtoms.mockResolvedValue(
    listAtomsResp([
      makeAtom({ id: "c1", confidence: "high", importance: "high" }),
      makeAtom({ id: "c2", confidence: "medium", importance: "low" }),
    ]),
  );
}

describe("<Overview />", () => {
  it("fans out to the 3 stats endpoints and renders overview metrics", async () => {
    stubStats();

    render(<Overview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("概览")).toBeInTheDocument();
    });

    expect(screen.getByText(/条记忆/)).toBeInTheDocument();
    expect(screen.getByText("记忆类型分布")).toBeInTheDocument();
    expect(screen.getByText("近 14 天新增趋势")).toBeInTheDocument();
    expect(screen.getByText("记忆构成")).toBeInTheDocument();
    expect(screen.getByText("置信度")).toBeInTheDocument();
    expect(screen.getByText("重要度")).toBeInTheDocument();

    expect(api.statsCounts).toHaveBeenCalledWith("ZYWZTD");
    expect(api.statsAtomKinds).toHaveBeenCalledWith("ZYWZTD");
    expect(api.statsGrowth).toHaveBeenCalledWith("ZYWZTD", 14);
  });

  it("renders KPI strip without Journal content", async () => {
    api.statsCounts.mockResolvedValue(
      statsCountsFixture({
        atoms: 127,
        entities: 18,
        episodes: 34,
        raw_events: 891,
        candidates_pending: 3,
        dirty_pages: 2,
      }),
    );
    api.statsAtomKinds.mockResolvedValue({ series: [] });
    api.statsGrowth.mockResolvedValue(statsGrowthFixture());
    api.listAtoms.mockResolvedValue(listAtomsResp([makeAtom({ id: "c1" })]));

    render(<Overview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getAllByText("127").length).toBeGreaterThanOrEqual(2);
    });

    expect(screen.getAllByText("18").length).toBeGreaterThan(0);
    expect(screen.getAllByText("34").length).toBeGreaterThan(0);
    expect(screen.getByText("待沉淀")).toBeInTheDocument();
    expect(screen.getByText("记忆条目")).toBeInTheDocument();
    expect(screen.getByText("关键人事物")).toBeInTheDocument();
    expect(screen.queryByText("891")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Promoted via dashboard/),
    ).not.toBeInTheDocument();
  });

  it("survives partial endpoint failures (Promise.allSettled)", async () => {
    api.statsCounts.mockRejectedValue(new Error("counts boom"));
    api.statsAtomKinds.mockRejectedValue(new Error("kinds boom"));
    api.statsGrowth.mockRejectedValue(new Error("growth boom"));
    api.listAtoms.mockRejectedValue(new Error("atoms boom"));

    render(<Overview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("概览")).toBeInTheDocument();
    });

    expect(screen.queryByText(/条记忆/)).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/暂无记忆类型数据|近 14 天暂无新增|暂无记忆构成数据/)
        .length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("renders subtitle when stats_counts returns custom values", async () => {
    api.statsCounts.mockResolvedValue(
      statsCountsFixture({ atoms: 147, entities: 22, raw_events: 234 }),
    );
    api.statsAtomKinds.mockResolvedValue({ series: [] });
    api.statsGrowth.mockResolvedValue({ series: [] });
    api.listAtoms.mockResolvedValue(listAtomsResp([]));

    render(<Overview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getAllByText("147").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("22").length).toBeGreaterThan(0);
    expect(screen.queryByText("234")).not.toBeInTheDocument();
  });

  it("does not crash when agentId is empty (no fan-out)", () => {
    render(<Overview agentId="" />);
    expect(api.statsCounts).not.toHaveBeenCalled();
    expect(api.statsAtomKinds).not.toHaveBeenCalled();
    expect(api.statsGrowth).not.toHaveBeenCalled();
  });

  it("refresh button triggers another stats fan-out without unmount", async () => {
    stubStats();

    render(<Overview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(api.statsCounts).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByRole("button");
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(api.statsCounts).toHaveBeenCalledTimes(2);
      expect(api.statsAtomKinds).toHaveBeenCalledTimes(2);
      expect(api.statsGrowth).toHaveBeenCalledTimes(2);
    });
  });
});
