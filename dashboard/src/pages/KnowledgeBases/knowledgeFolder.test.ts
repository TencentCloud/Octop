import { describe, expect, it } from "vitest";

import {
  buildKnowledgeFileTree,
  buildKnowledgeMoveTree,
  canMoveKnowledgeEntryTo,
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

  it("builds a folder tree and fills missing parents", () => {
    expect(
      buildKnowledgeFileTree([
        { filename: "readme.md", path: "readme.md" },
        { filename: "law.md", path: "notes/law/law.md" },
        { filename: "notes", path: "notes", is_dir: true },
      ]),
    ).toEqual([
      {
        key: "notes",
        path: "notes",
        name: "notes",
        isDir: true,
        children: [
          {
            key: "notes/law",
            path: "notes/law",
            name: "law",
            isDir: true,
            children: [],
          },
        ],
      },
    ]);
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

  it("offers every folder but the current one as a move target for a file", () => {
    const file = { filename: "act.md", path: "notes/law/act.md" };
    expect(canMoveKnowledgeEntryTo(file, "")).toBe(true);
    expect(canMoveKnowledgeEntryTo(file, "notes")).toBe(true);
    expect(canMoveKnowledgeEntryTo(file, "archive")).toBe(true);
    expect(canMoveKnowledgeEntryTo(file, "notes/law")).toBe(false);
  });

  it("never offers a folder itself or its subtree as its own target", () => {
    const folder = { filename: "notes", path: "notes", is_dir: true };
    expect(canMoveKnowledgeEntryTo(folder, "")).toBe(false);
    expect(canMoveKnowledgeEntryTo(folder, "notes")).toBe(false);
    expect(canMoveKnowledgeEntryTo(folder, "notes/law")).toBe(false);
    expect(canMoveKnowledgeEntryTo(folder, "notes-old")).toBe(true);
    expect(canMoveKnowledgeEntryTo(folder, "archive")).toBe(true);
  });

  it("lists every base as a move destination with its folders", () => {
    const tree = buildKnowledgeMoveTree(
      [
        { id: "kb1", name: "产品资料库" },
        { id: "kb2", name: "客服话术" },
      ],
      {
        kb1: [
          { path: "notes", filename: "notes", is_dir: true },
          { path: "notes/readme.md", filename: "readme.md" },
        ],
        kb2: [{ path: "faq/refund.md", filename: "refund.md" }],
      },
      { path: "notes/readme.md", filename: "readme.md" },
      "kb1",
    );

    expect(tree.map((node) => [node.key, node.name, node.disabled])).toEqual([
      ["kb1:", "产品资料库", false],
      ["kb2:", "客服话术", false],
    ]);
    expect(tree[0].children.map((node) => [node.key, node.disabled])).toEqual([
      ["kb1:notes", true],
    ]);
    expect(tree[1].children.map((node) => [node.key, node.disabled])).toEqual([
      ["kb2:faq", false],
    ]);
  });

  it("keeps a folder from moving into itself but not into another base", () => {
    const folder = { path: "notes", filename: "notes", is_dir: true };
    const tree = buildKnowledgeMoveTree(
      [
        { id: "kb1", name: "A" },
        { id: "kb2", name: "B" },
      ],
      {
        kb1: [folder, { path: "notes/law", filename: "law", is_dir: true }],
        kb2: [{ path: "notes", filename: "notes", is_dir: true }],
      },
      folder,
      "kb1",
    );

    expect(tree[0].disabled).toBe(true);
    expect(tree[0].children[0].disabled).toBe(true);
    expect(tree[0].children[0].children[0].disabled).toBe(true);
    expect(tree[1].disabled).toBe(false);
    expect(tree[1].children[0].disabled).toBe(false);
  });
});
