import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CronJobSpecOutput } from "../api/types";
import AutomationList from "./AutomationList";

const jobs = [
  {
    id: "job-active",
    name: "Daily report",
    enabled: true,
    schedule: { type: "cron", cron: "0 9 * * *", timezone: "Asia/Shanghai" },
    task_type: "text",
    text: "Create report",
  },
  {
    id: "job-paused",
    name: "Weekly report",
    enabled: false,
    schedule: { type: "cron", cron: "0 9 * * 1", timezone: "Asia/Shanghai" },
    task_type: "text",
    text: "Create report",
  },
] as CronJobSpecOutput[];
function props() {
  return {
    jobs,
    timeZone: "Asia/Shanghai",
    disabled: false,
    onDetail: vi.fn(),
    onEdit: vi.fn(),
    onExecuteNow: vi.fn(),
    onToggleEnabled: vi.fn(),
    onDelete: vi.fn(),
  };
}

describe("WorkBuddy automation binding", () => {
  it("dispatches detail, execution and toggle using real job identities", async () => {
    const handlers = props();
    render(<AutomationList {...handlers} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Daily report", exact: true }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "cronJobs.executeNow: Daily report" }),
    );
    await userEvent.click(
      screen.getByRole("switch", { name: "common.disable: Daily report" }),
    );
    expect(handlers.onDetail).toHaveBeenCalledExactlyOnceWith(jobs[0]);
    expect(handlers.onExecuteNow).toHaveBeenCalledExactlyOnceWith(jobs[0]);
    expect(handlers.onToggleEnabled).toHaveBeenCalledExactlyOnceWith(jobs[0]);
    expect(
      screen.getByRole("switch", { name: "common.disable: Daily report" }),
    ).toBeChecked();
  });
  it("preserves Octop's restriction on editing or deleting enabled jobs", async () => {
    const handlers = props();
    render(<AutomationList {...handlers} />);
    await userEvent.click(
      screen.getByRole("button", { name: "common.more: Daily report" }),
    );
    const menu = screen.getByRole("menu");
    expect(
      within(menu).getByRole("menuitem", { name: "common.edit" }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(
      within(menu).getByRole("menuitem", { name: "common.delete" }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(handlers.onEdit).not.toHaveBeenCalled();
    expect(handlers.onDelete).not.toHaveBeenCalled();
  });
  it("blocks mutations while the owner page is refreshing", () => {
    const handlers = props();
    render(<AutomationList {...handlers} disabled />);
    expect(
      screen.getByRole("button", { name: "cronJobs.executeNow: Daily report" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("switch", { name: "common.disable: Daily report" }),
    ).toBeDisabled();
  });
});
