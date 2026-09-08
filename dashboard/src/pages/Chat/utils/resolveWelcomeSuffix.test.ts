import { describe, expect, it } from "vitest";
import { resolveWelcomeSuffix } from "./resolveWelcomeSuffix";

describe("resolveWelcomeSuffix", () => {
  it("prefers non-empty description over welcome message", () => {
    expect(resolveWelcomeSuffix("系统描述", "模板欢迎语")).toBe("系统描述");
  });

  it("falls back to welcome message when description is empty", () => {
    expect(resolveWelcomeSuffix("", "模板欢迎语")).toBe("模板欢迎语");
  });

  it("treats whitespace-only description as empty", () => {
    expect(resolveWelcomeSuffix("   ", "模板欢迎语")).toBe("模板欢迎语");
  });

  it("falls back when description is null", () => {
    expect(resolveWelcomeSuffix(null, "模板欢迎语")).toBe("模板欢迎语");
  });

  it("returns null when both are null", () => {
    expect(resolveWelcomeSuffix(null, null)).toBeNull();
  });

  it("trims description before returning", () => {
    expect(resolveWelcomeSuffix("  有空格  ", "x")).toBe("有空格");
  });

  it("returns null when both are undefined", () => {
    expect(resolveWelcomeSuffix(undefined, undefined)).toBeNull();
  });
});
