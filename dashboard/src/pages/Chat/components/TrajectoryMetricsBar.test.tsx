import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TrajectoryMetrics } from "../../../api/modules/trajectory";
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
});
