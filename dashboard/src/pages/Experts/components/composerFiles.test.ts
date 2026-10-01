import { describe, expect, it } from "vitest";

import {
  diffComposerFiles,
  ensurePromptFiles,
  removeComposerSkill,
  removeComposerSubagent,
  upsertComposerFile,
} from "./composerFiles";

describe("diffComposerFiles", () => {
  it("reports edited, added, and removed files", () => {
    expect(
      diffComposerFiles(
        [
          { name: "AGENTS.md", content: "old" },
          { name: "skills/demo/SKILL.md", content: "keep" },
        ],
        [
          { name: "AGENTS.md", content: "new" },
          { name: "skills/extra/SKILL.md", content: "added" },
        ],
      ),
    ).toEqual({
      file_overrides: [
        { name: "AGENTS.md", content: "new" },
        { name: "skills/extra/SKILL.md", content: "added" },
      ],
      omit_files: ["skills/demo/SKILL.md"],
    });
  });
});

describe("composer file helpers", () => {
  it("adds AGENTS.md when the template omitted it", () => {
    expect(ensurePromptFiles([{ name: "SOUL.md", content: "s" }])).toEqual([
      { name: "SOUL.md", content: "s" },
      { name: "AGENTS.md", content: "" },
    ]);
  });

  it("upserts and removes skill files", () => {
    const next = upsertComposerFile([{ name: "AGENTS.md", content: "a" }], {
      name: "AGENTS.md",
      content: "b",
    });
    expect(next).toEqual([{ name: "AGENTS.md", content: "b" }]);
    expect(
      removeComposerSkill(
        [
          { name: "AGENTS.md", content: "b" },
          { name: "skills/demo/SKILL.md", content: "x" },
          { name: "skills/demo/notes.md", content: "y" },
        ],
        "demo",
      ),
    ).toEqual([{ name: "AGENTS.md", content: "b" }]);
    expect(
      removeComposerSubagent(
        [
          { name: "AGENTS.md", content: "b" },
          { name: "agents/reviewer.md", content: "r" },
        ],
        "reviewer",
      ),
    ).toEqual([{ name: "AGENTS.md", content: "b" }]);
  });
});
