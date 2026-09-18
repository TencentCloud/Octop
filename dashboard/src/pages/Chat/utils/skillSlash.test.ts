import { describe, expect, it } from "vitest";
import { insertSkillSlash, mentionedSkillSlugs } from "./skillSlash";

const SKILLS = [{ slug: "web-search" }, { slug: "note" }];

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

describe("mentionedSkillSlugs", () => {
  it("returns the leading invoked slug", () => {
    expect(mentionedSkillSlugs("/web-search look this up", SKILLS)).toEqual([
      "web-search",
    ]);
  });

  it("returns empty for plain text without a leading token", () => {
    expect(mentionedSkillSlugs("please help", SKILLS)).toEqual([]);
  });

  it("ignores mid-text slash tokens", () => {
    expect(
      mentionedSkillSlugs("用这个技能 /web-search 写报告", SKILLS),
    ).toEqual([]);
  });

  it("returns empty for a leading token that is not a known skill", () => {
    expect(mentionedSkillSlugs("/unknown args", SKILLS)).toEqual([]);
  });

  it("does not treat paths as a leading slash token", () => {
    expect(mentionedSkillSlugs("/root/ddd", SKILLS)).toEqual([]);
  });
});
