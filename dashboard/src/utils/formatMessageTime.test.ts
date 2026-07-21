import { afterEach, describe, expect, it, vi } from "vitest";
import {
  calendarDaysAgo,
  formatMessageTime,
  formatServerDateTime,
  formatServerHourMinute,
  formatServerIsoDateTime,
  formatServerYmd,
} from "./formatMessageTime";

function hourInZone(tsMs: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour: "numeric",
    hour12: false,
  }).formatToParts(new Date(tsMs));
  return Number(parts.find((part) => part.type === "hour")?.value);
}

describe("formatMessageTime", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("uses server timezone instead of browser local time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-09T12:00:00Z"));

    const utcMorning = Date.UTC(2026, 6, 9, 7, 16, 37);
    expect(hourInZone(utcMorning, "Asia/Shanghai")).toBe(15);
    expect(hourInZone(utcMorning, "UTC")).toBe(7);
    expect(formatMessageTime(utcMorning, "Asia/Shanghai")).toBeTruthy();
    expect(formatMessageTime(utcMorning, "UTC")).toBeTruthy();
  });
});

describe("formatServerDateTime", () => {
  it("formats epoch seconds in the configured timezone", () => {
    const epochSec = Date.UTC(2026, 6, 9, 7, 16, 37) / 1000;
    expect(hourInZone(epochSec * 1000, "Asia/Shanghai")).toBe(15);
    expect(formatServerDateTime(epochSec, "Asia/Shanghai")).toContain("2026");
  });
});

describe("formatServerIsoDateTime", () => {
  it("formats ISO strings in the configured timezone", () => {
    const iso = "2026-07-09T07:16:37+00:00";
    const ts = Date.parse(iso);
    expect(hourInZone(ts, "Asia/Shanghai")).toBe(15);
    expect(hourInZone(ts, "UTC")).toBe(7);
    expect(formatServerIsoDateTime(iso, "Asia/Shanghai")).toBeTruthy();
    expect(formatServerIsoDateTime(iso, "UTC")).toBeTruthy();
  });

  it("returns em dash for empty input", () => {
    expect(formatServerIsoDateTime("", "UTC")).toBe("—");
  });
});

describe("formatServerYmd / formatServerHourMinute / calendarDaysAgo", () => {
  it("formats calendar parts in Asia/Shanghai", () => {
    // 2026-07-09 16:30 CST = 08:30 UTC
    const iso = "2026-07-09T08:30:00Z";
    expect(formatServerYmd(iso, "Asia/Shanghai")).toBe("2026-07-09");
    expect(formatServerHourMinute(iso, "Asia/Shanghai")).toBe("16:30");
    expect(formatServerHourMinute(iso, "UTC")).toBe("08:30");
  });

  it("computes calendar day distance in the configured zone", () => {
    const now = new Date("2026-07-10T02:00:00Z");
    expect(calendarDaysAgo("2026-07-09T08:00:00Z", "Asia/Shanghai", now)).toBe(
      1,
    );
    expect(calendarDaysAgo("2026-07-09T08:00:00Z", "UTC", now)).toBe(1);
  });
});
