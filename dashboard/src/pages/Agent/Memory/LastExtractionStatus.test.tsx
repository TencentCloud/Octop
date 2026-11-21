import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import LastExtractionStatus from "./LastExtractionStatus";

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));

describe("last memory extraction", () => {
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
