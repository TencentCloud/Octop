import { describe, expect, it } from "vitest";
import {
  formatCompactCount,
  formatExactCount,
  usageCountDisplay,
} from "./formatUsageCount";

describe("formatCompactCount", () => {
  it("keeps counts that fit the card exact", () => {
    expect(formatCompactCount(15, "zh")).toBe("15");
    expect(formatCompactCount(24_315, "zh")).toBe("24,315");
    expect(formatCompactCount(185_898, "en")).toBe("185,898");
    expect(formatCompactCount(999_999, "zh")).toBe("999,999");
  });

  it("uses 万 and 亿 for Chinese", () => {
    expect(formatCompactCount(1_000_000, "zh")).toBe("100万");
    expect(formatCompactCount(2_788_473, "zh")).toBe("278.8万");
    expect(formatCompactCount(12_345_678_901, "zh")).toBe("123.5亿");
    expect(formatCompactCount(1_230_000_000_000, "zh")).toBe("1.23万亿");
  });

  it("uses M, B, and T for English", () => {
    expect(formatCompactCount(1_000_000, "en")).toBe("1M");
    expect(formatCompactCount(2_788_473, "en")).toBe("2.79M");
    expect(formatCompactCount(12_345_678_901, "en")).toBe("12.3B");
    expect(formatCompactCount(1_230_000_000_000, "en")).toBe("1.23T");
  });

  it("promotes a rounded 1000 of a smaller unit", () => {
    expect(formatCompactCount(999_950_000, "en")).toBe("1B");
    expect(formatCompactCount(99_999_999, "zh")).toBe("1亿");
  });

  it("keeps the sign and rejects non-finite values", () => {
    expect(formatCompactCount(-2_788_473, "en")).toBe("-2.79M");
    expect(formatCompactCount(Number.NaN, "zh")).toBe("0");
  });
});

describe("usageCountDisplay", () => {
  it("omits the exact line when the card already shows the full number", () => {
    expect(usageCountDisplay(15, "zh")).toEqual({ value: "15" });
    expect(usageCountDisplay(185_898, "en")).toEqual({ value: "185,898" });
  });

  it("pairs the compact card text with a grouped exact count", () => {
    expect(usageCountDisplay(2_788_473, "zh")).toEqual({
      value: "278.8万",
      exact: "2,788,473",
    });
    expect(formatExactCount(2_788_473.4, "en")).toBe("2,788,473.4");
  });
});
