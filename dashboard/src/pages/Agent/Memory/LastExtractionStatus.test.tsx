import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import LastExtractionStatus from "./LastExtractionStatus";

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));

describe("last memory extraction", () => {
  const codex = {
    timestamp: "2026-11-24T08:52:00Z",
    status: "captured" as const,
    proposals: 0,
  };
  const failure = {
    timestamp: "2026-11-24T08:43:00Z",
    failure_reason: "no LLM backend configured",
  };

  it("keeps the earlier server warning in collapsed history", () => {
    render(<LastExtractionStatus codex={codex} run={failure} />);
    expect(screen.getByText("原文已上报，尚无复核结果记录")).toBeVisible();
    expect(screen.getByText("最近提取未完成，已降级")).not.toBeVisible();
    const summary = screen.getByText(/上一次服务端提取/);
    summary.click();
    expect(screen.getByText("最近提取未完成，已降级")).toBeVisible();
  });

  it("shows a newer server failure, and distinguishes completion from submission", () => {
    const run = { ...failure, timestamp: "2026-11-24T09:05:00Z" };
    const { rerender } = render(
      <LastExtractionStatus
        run={run}
        codex={{ ...codex, status: "finished_without_proposal" }}
      />,
    );
    expect(screen.getByText("最近提取未完成，已降级")).toBeVisible();
    expect(screen.getByText("复核续轮已结束，未收到候选")).toBeVisible();
    rerender(
      <LastExtractionStatus
        codex={{ ...codex, status: "proposed", proposals: 1 }}
      />,
    );
    expect(screen.getByText(/已提交.*候选/)).toBeVisible();
  });
  it.each([
    ["APITimeoutError: Request timed out.", "最近提取超时，已降级"],
    ["ReadTimeout", "最近提取超时，已降级"],
    ["invalid JSON", "最近提取未完成，已降级"],
  ])("shows %s and the failure details", (failure_reason, label) => {
    render(<LastExtractionStatus run={{ failure_reason }} />);
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.getByText(failure_reason)).toBeInTheDocument();
  });

  it("distinguishes a quiet run from success and formats server time", () => {
    const timestamp = "2026-10-14T01:30:00Z";
    const { rerender } = render(
      <LastExtractionStatus run={{ timestamp, quiet: true }} />,
    );
    expect(screen.getByText("最近提取完成，无新增记忆")).toBeVisible();
    expect(
      screen.getByText(formatServerIsoDateTime(timestamp, "Asia/Shanghai")),
    ).toBeVisible();
    rerender(<LastExtractionStatus run={{ timestamp, quiet: false }} />);
    expect(screen.getByText("最近提取成功")).toBeVisible();
  });
});
