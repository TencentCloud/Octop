import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TrajectoryMetrics } from "../../../api/modules/trajectory";

const exportMock = vi.fn();

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

import TrajectoryMetricsBar from "./TrajectoryMetricsBar";

const metrics: TrajectoryMetrics = {
  turns: 2,
  steps: 5,
  llm_duration_ms: null,
  tool_duration_ms: 40,
  ttft_avg_ms: null,
  tok_per_s: 0,
  cache_hit_ratio: null,
  input_tokens: 10,
  output_tokens: null,
  cache_read_tokens: null,
};

describe("TrajectoryMetricsBar", () => {
  beforeEach(() => {
    exportMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hides null metric fields and keeps zeros", () => {
    const { container } = render(
      <TrajectoryMetricsBar agentId="A1" threadId="T1" metrics={metrics} />,
    );

    expect(container.querySelector('[data-metric="turns"]')).not.toBeNull();
    expect(container.querySelector('[data-metric="steps"]')).not.toBeNull();
    expect(
      container.querySelector('[data-metric="tool_duration_ms"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('[data-metric="tok_per_s"]'),
    ).toHaveTextContent("0");
    expect(
      container.querySelector('[data-metric="input_tokens"]'),
    ).not.toBeNull();

    expect(
      container.querySelector('[data-metric="llm_duration_ms"]'),
    ).toBeNull();
    expect(container.querySelector('[data-metric="ttft_avg_ms"]')).toBeNull();
    expect(
      container.querySelector('[data-metric="cache_hit_ratio"]'),
    ).toBeNull();
    expect(container.querySelector('[data-metric="output_tokens"]')).toBeNull();
    expect(
      container.querySelector('[data-metric="cache_read_tokens"]'),
    ).toBeNull();
  });

  it("triggers a blob download URL when export is clicked", async () => {
    const blob = new Blob(["{}\n"], { type: "application/x-ndjson" });
    exportMock.mockResolvedValue(blob);
    const createObjectURL = vi.fn(() => "blob:trajectory-export");
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    render(
      <TrajectoryMetricsBar agentId="A1" threadId="T1" metrics={metrics} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => {
      expect(exportMock).toHaveBeenCalledWith("A1", "T1");
      expect(createObjectURL).toHaveBeenCalledWith(blob);
      expect(click).toHaveBeenCalled();
    });
  });
});
