import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { decisionApi, type LayaStatus } from "../../../../api/modules/decision";
import { LayaLocalInstall } from "./LayaLocalInstall";

vi.mock("../../../../api/modules/decision", () => ({
  decisionApi: {
    layaStatus: vi.fn(),
  },
}));

const running: LayaStatus = {
  installed: true,
  running: true,
  managed: true,
  phase: "running",
  endpoint: "http://127.0.0.1:8000/v1/systemone",
  port: 8000,
  command: "",
  logs: [],
};

describe("LayaLocalInstall", () => {
  beforeEach(() => {
    vi.mocked(decisionApi.layaStatus).mockResolvedValue(running);
  });

  it("separates service readiness from being the active default", async () => {
    const onStatusChange = vi.fn();
    const { rerender } = render(
      <LayaLocalInstall
        active={false}
        onReady={vi.fn()}
        onStatusChange={onStatusChange}
      />,
    );

    expect(
      await screen.findByText("models.decisionServiceReady"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("models.decisionDefaultInactive"),
    ).toBeInTheDocument();
    expect(onStatusChange).toHaveBeenCalledWith(running);

    rerender(
      <LayaLocalInstall
        active
        onReady={vi.fn()}
        onStatusChange={onStatusChange}
      />,
    );
    expect(
      screen.getByText("models.decisionDefaultActive"),
    ).toBeInTheDocument();
  });
});
