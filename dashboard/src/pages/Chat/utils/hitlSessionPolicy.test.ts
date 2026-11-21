import { describe, expect, it } from "vitest";
import {
  isHitlBypassPolicy,
  mergeAllowTools,
  parseHitlSessionPolicy,
  withoutAllowTools,
} from "./hitlSessionPolicy";

describe("hitlSessionPolicy", () => {
  it("parses allow-all and allow-tools", () => {
    expect(parseHitlSessionPolicy({ mode: "allow_all" })).toEqual({
      mode: "allow_all",
    });
    expect(
      parseHitlSessionPolicy({ mode: "allow_tools", tools: ["execute"] }),
    ).toEqual({ mode: "allow_tools", tools: ["execute"] });
    expect(parseHitlSessionPolicy({ mode: "allow_tools", tools: [] })).toEqual({
      mode: "ask",
    });
    expect(parseHitlSessionPolicy(undefined)).toEqual({ mode: "ask" });
  });

  it("treats only bypass modes as visible policy chips", () => {
    expect(isHitlBypassPolicy({ mode: "ask" })).toBe(false);
    expect(isHitlBypassPolicy({ mode: "allow_all" })).toBe(true);
    expect(
      isHitlBypassPolicy({ mode: "allow_tools", tools: ["write_file"] }),
    ).toBe(true);
  });

  it("merges extra tool names onto an allow-tools policy", () => {
    expect(mergeAllowTools({ mode: "ask" }, ["execute"])).toEqual({
      mode: "allow_tools",
      tools: ["execute"],
    });
    expect(
      mergeAllowTools({ mode: "allow_tools", tools: ["execute"] }, [
        "write_file",
        "execute",
      ]),
    ).toEqual({ mode: "allow_tools", tools: ["execute", "write_file"] });
    expect(mergeAllowTools({ mode: "allow_all" }, ["execute"])).toEqual({
      mode: "allow_all",
    });
  });

  it("removes a tool and falls back to ask when none remain", () => {
    expect(
      withoutAllowTools(
        { mode: "allow_tools", tools: ["execute", "write_file"] },
        "write_file",
      ),
    ).toEqual({ mode: "allow_tools", tools: ["execute"] });
    expect(
      withoutAllowTools({ mode: "allow_tools", tools: ["execute"] }, "execute"),
    ).toEqual({ mode: "ask" });
  });
});
