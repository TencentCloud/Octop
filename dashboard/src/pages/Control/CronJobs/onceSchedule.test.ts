import { describe, expect, it } from "vitest";

import {
  defaultOnceRunAt,
  formatOnceWallClock,
  formatServerWallClock,
  formatTriggerText,
  isFutureWallClock,
  oneShotPhase,
  scheduleFieldFromTrigger,
} from "./onceSchedule";

describe("onceSchedule", () => {
  it("formats a server wall clock without shifting the instant", () => {
    const stamp = new Date("2026-10-17T01:30:00Z");
    expect(formatServerWallClock(stamp, "Asia/Shanghai")).toBe(
      "2026-10-17T09:30:00",
    );
    expect(formatServerWallClock(stamp, "UTC")).toBe("2026-10-17T01:30:00");
  });

  it("defaults a one-shot to one hour ahead in the server timezone", () => {
    const now = new Date("2026-10-17T15:45:00Z");
    expect(defaultOnceRunAt("Asia/Shanghai", now)).toBe("2026-10-18T00:45:00");
  });

  it("compares future wall clocks in the server timezone", () => {
    const now = new Date("2026-10-17T01:30:00Z");
    expect(isFutureWallClock("2026-10-17T09:31:00", "Asia/Shanghai", now)).toBe(
      true,
    );
    expect(isFutureWallClock("2026-10-17T09:30:00", "Asia/Shanghai", now)).toBe(
      false,
    );
  });

  it("labels date and mail triggers for the list", () => {
    expect(formatOnceWallClock("2026-10-18T09:00:00")).toBe("2026-10-18 09:00");
    expect(
      formatTriggerText("date:2026-10-18T09:00:00", {
        mail: "mail",
        once: "Once",
      }),
    ).toBe("Once · 2026-10-18 09:00");
    expect(
      formatTriggerText("agently:box", { mail: "New mail", once: "Once" }),
    ).toBe("New mail");
    expect(scheduleFieldFromTrigger("cron:0 9 * * *")).toBe("0 9 * * *");
  });

  it("derives one-shot phases from enabled and last status", () => {
    expect(oneShotPhase("cron:0 9 * * *", true, null)).toBeNull();
    expect(oneShotPhase("date:2026-10-18T09:00:00", true, null)).toBe(
      "pending",
    );
    expect(oneShotPhase("date:2026-10-18T09:00:00", false, "ok")).toBe("done");
    expect(oneShotPhase("date:2026-10-18T09:00:00", false, "error")).toBe(
      "failed",
    );
    expect(oneShotPhase("date:2026-10-18T09:00:00", false, "missed")).toBe(
      "missed",
    );
    expect(oneShotPhase("date:2026-10-18T09:00:00", false, null)).toBe(
      "paused",
    );
  });
});
