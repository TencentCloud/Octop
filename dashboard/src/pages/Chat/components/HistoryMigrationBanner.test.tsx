import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { HistoryMigrationStatus } from "../../../api/modules/octopThreads";
import HistoryMigrationBanner from "./HistoryMigrationBanner";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const idleStatus: HistoryMigrationStatus = {
  remaining: 1,
  pending: 1,
  queued: 0,
  running: 0,
  failed: 0,
  processing: false,
  agent_busy: false,
  can_start: true,
};

describe("HistoryMigrationBanner", () => {
  it("shows an indeterminate progress bar only while migration is processing", () => {
    const { rerender } = render(
      <HistoryMigrationBanner
        status={idleStatus}
        starting={false}
        startFailed={false}
        onStart={vi.fn()}
      />,
    );

    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();

    rerender(
      <HistoryMigrationBanner
        status={{ ...idleStatus, processing: true, pending: 0, running: 1 }}
        starting={false}
        startFailed={false}
        onStart={vi.fn()}
      />,
    );

    const progress = screen.getByRole("progressbar");
    expect(progress).toHaveAttribute(
      "aria-label",
      "chat.historyMigration.running",
    );
    expect(progress).not.toHaveAttribute("aria-valuenow");
  });
});
