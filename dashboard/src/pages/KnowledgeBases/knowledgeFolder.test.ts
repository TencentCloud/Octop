import { describe, expect, it } from "vitest";

import {
  isDirectKnowledgeChild,
  joinKnowledgePath,
  knowledgeBasename,
  knowledgeBreadcrumb,
  normalizeKnowledgePath,
  shouldOpenKnowledgeFolder,
} from "./knowledgeFolder";

describe("knowledgeFolder", () => {
  it("normalizes nested paths", () => {
    expect(normalizeKnowledgePath("/a/b/c.md")).toBe("a/b/c.md");
    expect(knowledgeBasename("notes/readme.md")).toBe("readme.md");
    expect(joinKnowledgePath("notes", "readme.md")).toBe("notes/readme.md");
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

  it("does not enter a folder when the click comes from rename/actions", () => {
    const actions = document.createElement("div");
    actions.setAttribute("data-kb-doc-actions", "");
    const renameButton = document.createElement("button");
    actions.appendChild(renameButton);
    document.body.appendChild(actions);

    expect(shouldOpenKnowledgeFolder(true, { target: renameButton })).toBe(
      false,
    );
    actions.remove();
  });

  it("enters a folder when clicking the folder entry itself", () => {
    const card = document.createElement("div");
    expect(shouldOpenKnowledgeFolder(true, { target: card })).toBe(true);
  });

  it("does not navigate for files", () => {
    const card = document.createElement("div");
    expect(shouldOpenKnowledgeFolder(false, { target: card })).toBe(false);
  });
});
