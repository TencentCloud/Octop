import { describe, expect, it } from "vitest";

import {
  isDirectKnowledgeChild,
  joinKnowledgePath,
  knowledgeBasename,
  knowledgeBreadcrumb,
  knowledgeFileNameParts,
  knowledgePathParent,
  normalizeKnowledgePath,
} from "./knowledgePath";

describe("knowledgePath", () => {
  it("normalizes nested paths", () => {
    expect(normalizeKnowledgePath("/a/b/c.md")).toBe("a/b/c.md");
    expect(knowledgeBasename("notes/readme.md")).toBe("readme.md");
    expect(joinKnowledgePath("notes", "readme.md")).toBe("notes/readme.md");
  });

  it("splits a file name from its suffix", () => {
    expect(knowledgeFileNameParts("notes/readme.md")).toEqual({
      stem: "readme",
      suffix: ".md",
    });
    expect(knowledgeFileNameParts("a.b.pdf")).toEqual({
      stem: "a.b",
      suffix: ".pdf",
    });
    expect(knowledgeFileNameParts("README")).toEqual({
      stem: "README",
      suffix: "",
    });
    expect(knowledgeFileNameParts(".gitignore")).toEqual({
      stem: ".gitignore",
      suffix: "",
    });
  });

  it("returns parent folder", () => {
    expect(knowledgePathParent("notes/a.md")).toBe("notes");
    expect(knowledgePathParent("a.md")).toBe("");
  });

  it("lists immediate children only", () => {
    expect(isDirectKnowledgeChild("notes", "")).toBe(true);
    expect(isDirectKnowledgeChild("notes/readme.md", "")).toBe(false);
    expect(isDirectKnowledgeChild("notes/readme.md", "notes")).toBe(true);
    expect(isDirectKnowledgeChild("notes/deep/file.md", "notes")).toBe(false);
  });

  it("builds breadcrumb segments", () => {
    expect(knowledgeBreadcrumb("notes/law", "知识库")).toEqual([
      { label: "知识库", path: "" },
      { label: "notes", path: "notes" },
      { label: "law", path: "notes/law" },
    ]);
  });
});
