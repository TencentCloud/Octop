import { describe, expect, it } from "vitest";

import { groupExpertFiles } from "./expertFileGroups";

describe("groupExpertFiles", () => {
  it("separates config markdown, skills, and subagents", () => {
    const { configFiles, skillGroups, subagentFiles } = groupExpertFiles([
      { name: "SOUL.md", content: "# Soul" },
      { name: "AGENTS.md", content: "# Agents guide" },
      {
        name: "skills/demo/SKILL.md",
        content:
          '---\nname: Demo Skill\ndescription: A demo\nmetadata:\n  octop:\n    emoji: "🎯"\n---\n\n# Skill',
      },
      {
        name: "agents/reviewer.md",
        content:
          "---\nname: Reviewer\ndescription: Review code\nemoji: 🔍\n---\n\n# Body\n",
      },
    ]);

    expect(configFiles.map((f) => f.name)).toEqual(["SOUL.md", "AGENTS.md"]);
    expect(skillGroups).toHaveLength(1);
    expect(skillGroups[0]?.name).toBe("demo");
    expect(skillGroups[0]?.emoji).toBe("🎯");
    expect(skillGroups[0]?.displayName).toBe("Demo Skill");
    expect(skillGroups[0]?.description).toBe("A demo");
    expect(subagentFiles).toHaveLength(1);
    expect(subagentFiles[0]?.slug).toBe("reviewer");
    expect(subagentFiles[0]?.name).toBe("Reviewer");
    expect(subagentFiles[0]?.description).toBe("Review code");
    expect(subagentFiles[0]?.emoji).toBe("🔍");
  });

  it("excludes manifest.json from config preview", () => {
    const { configFiles } = groupExpertFiles([
      { name: "SOUL.md", content: "# Soul" },
      { name: "manifest.json", content: "{}" },
    ]);
    expect(configFiles.map((f) => f.name)).toEqual(["SOUL.md"]);
  });
});
