import { describe, expect, it } from "vitest";
import { insertSkillSlash } from "./skillSlash";

describe("insertSkillSlash", () => {
  it("inserts /slug into empty composer", () => {
    expect(insertSkillSlash("", "web-search")).toBe("/web-search ");
  });

  it("appends /slug after existing text", () => {
    expect(insertSkillSlash("please", "web-search")).toBe(
      "please /web-search ",
    );
  });

  it("replaces a leading slash token and keeps args", () => {
    expect(insertSkillSlash("/old look this up", "web-search")).toBe(
      "/web-search look this up",
    );
  });

  it("does not treat paths as a leading slash token", () => {
    expect(insertSkillSlash("/root/ddd", "web-search")).toBe(
      "/root/ddd /web-search ",
    );
  });
});
