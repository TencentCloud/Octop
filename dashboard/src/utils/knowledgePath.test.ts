import { describe, expect, it } from "vitest";

import {
  isDirectKnowledgeChild,
  joinKnowledgePath,
  joinKnowledgeRelativePath,
  knowledgeBasename,
  knowledgeBreadcrumb,
  knowledgePathParent,
  normalizeKnowledgePath,
} from "./knowledgePath";

describe("knowledgePath", () => {
  it("normalizes nested paths", () => {
    expect(normalizeKnowledgePath("/a/b/c.md")).toBe("a/b/c.md");
    expect(knowledgeBasename("notes/readme.md")).toBe("readme.md");
    expect(joinKnowledgePath("notes", "readme.md")).toBe("notes/readme.md");
  });

  it("joins a folder with a nested relative path", () => {
    expect(joinKnowledgeRelativePath("", "资料/子目录/a.txt")).toBe(
      "资料/子目录/a.txt",
    );
    expect(joinKnowledgeRelativePath("现有目录/", "资料/子目录/a.txt")).toBe(
      "现有目录/资料/子目录/a.txt",
    );
    expect(joinKnowledgeRelativePath("./notes/", "a\\b.txt")).toBe(
      "notes/a/b.txt",
    );
    expect(joinKnowledgeRelativePath("notes", "")).toBe("notes");
    expect(() => joinKnowledgeRelativePath("notes/..", "a.txt")).toThrow(
      "invalid knowledge path",
    );
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
