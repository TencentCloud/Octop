import { describe, expect, it } from "vitest";
import { packageSkillRelativePath } from "./SkillFileTree";

describe("packageSkillRelativePath", () => {
  it("strips the skill root prefix", () => {
    expect(
      packageSkillRelativePath(
        "/skills/demo/references/guide.md",
        "/skills/demo",
      ),
    ).toBe("references/guide.md");
    expect(
      packageSkillRelativePath("skills/demo/SKILL.md", "skills/demo"),
    ).toBe("SKILL.md");
  });

  it("returns empty string for the skill root itself", () => {
    expect(packageSkillRelativePath("/skills/demo", "/skills/demo")).toBe("");
    expect(packageSkillRelativePath("skills/demo/", "skills/demo")).toBe("");
  });
});
