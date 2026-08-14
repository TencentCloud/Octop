import { describe, expect, it } from "vitest";
import { buildSkillMarkdown } from "./components/SkillDrawer";
import {
  isSkillManifestPath,
  parseSkillPreviewFromMarkdown,
  skillDirectoryPath,
  skillManifestPath,
} from "./skillMarkdown";

describe("parseSkillPreviewFromMarkdown", () => {
  it("reads name, description, and octop emoji from SKILL.md", () => {
    const md = buildSkillMarkdown({
      name: "My Skill",
      description: "Does work",
      emoji: "🛠️",
      metadata: [],
      body: "Body",
    });
    expect(parseSkillPreviewFromMarkdown(md, "my-skill")).toEqual({
      emoji: "🛠️",
      name: "My Skill",
      description: "Does work",
    });
  });
});

describe("isSkillManifestPath", () => {
  it("matches SKILL.md paths", () => {
    expect(isSkillManifestPath("/skills/foo/SKILL.md")).toBe(true);
    expect(isSkillManifestPath("notes.txt")).toBe(false);
  });
});

describe("skillDirectoryPath", () => {
  it("maps workspace and builtin roots", () => {
    expect(skillDirectoryPath({ kind: "workspace", slug: "demo" })).toBe(
      "/skills/demo",
    );
    expect(skillDirectoryPath({ kind: "builtin", slug: "demo" })).toBe(
      "/_builtin_skills/demo",
    );
  });

  it("builds manifest path", () => {
    expect(skillManifestPath({ kind: "workspace", slug: "demo" })).toBe(
      "/skills/demo/SKILL.md",
    );
  });
});
