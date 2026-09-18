import { describe, expect, it } from "vitest";
import zh from "./zh.json";
import en from "./en.json";

describe("#690 skill library rename", () => {
  it("zh user-facing nav uses 技能库 not 技能包", () => {
    expect(zh.nav.skillPackages).toBe("技能库");
    expect(zh.skillPackages.title).toBe("技能库");
    expect(JSON.stringify(zh)).not.toContain("技能包");
  });

  it("en user-facing titles use Skill Libraries", () => {
    expect(en.nav.skillPackages).toBe("Skill Libraries");
    expect(en.skillPackages.title).toBe("Skill Libraries");
    expect(en.skillPackages.createPackage).toBe("Create Skill Library");
    expect(en.skillPackages.editPackage).toBe("Edit Skill Library");
  });
});
