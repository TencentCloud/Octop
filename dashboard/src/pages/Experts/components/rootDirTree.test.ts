import { describe, expect, it } from "vitest";
import {
  ancestorDirPaths,
  ancestorDirPathsInForest,
  appendChildren,
  commitTypedAbsolutePath,
  insertChild,
  isExplicitAbsolutePath,
  isPathUnderHome,
  pathExistsInTree,
  renameNode,
  sanitizeForest,
  sanitizeTree,
  type DirTreeNode,
} from "./rootDirTree";

const root: DirTreeNode = { value: "/", title: "/", isLeaf: false };

describe("rootDirTree helpers", () => {
  it("insertChild adds a directory under its parent", () => {
    const withParent: DirTreeNode[] = [
      {
        ...root,
        children: [{ value: "/Users", title: "Users", isLeaf: false }],
      },
    ];
    const next = insertChild(withParent, "/Users", {
      value: "/Users/New Folder",
      title: "New Folder",
      isLeaf: false,
    });
    expect(next[0].children?.[0].children).toEqual([
      { value: "/Users/New Folder", title: "New Folder", isLeaf: false },
    ]);
  });

  it("renameNode updates path and title under the same parent", () => {
    const tree: DirTreeNode[] = [
      {
        ...root,
        children: [
          {
            value: "/Users",
            title: "Users",
            isLeaf: false,
            children: [
              {
                value: "/Users/New Folder",
                title: "New Folder",
                isLeaf: false,
              },
            ],
          },
        ],
      },
    ];
    const next = renameNode(
      tree,
      "/Users/New Folder",
      "/Users/workspace",
      "workspace",
    );
    expect(next[0].children?.[0].children).toEqual([
      { value: "/Users/workspace", title: "workspace", isLeaf: false },
    ]);
  });

  it("appendChildren merges without duplicating paths", () => {
    const tree: DirTreeNode[] = [
      {
        ...root,
        children: [{ value: "/a", title: "a", isLeaf: false }],
      },
    ];
    const next = appendChildren(tree, "/", [
      { value: "/a", title: "a", isLeaf: false },
      { value: "/b", title: "b", isLeaf: false },
    ]);
    expect(next[0].children?.map((c) => c.value)).toEqual(["/a", "/b"]);
  });

  it("sanitizeTree drops root-level duplicates that already exist under /", () => {
    const tree: DirTreeNode[] = [
      {
        ...root,
        children: [
          {
            value: "/Users",
            title: "Users",
            isLeaf: false,
            children: [
              {
                value: "/Users/jubaoliang",
                title: "jubaoliang",
                isLeaf: false,
              },
            ],
          },
        ],
      },
      {
        value: "/Users/jubaoliang",
        title: "/Users/jubaoliang",
        isLeaf: false,
      },
      {
        value: "/Users/jubaoliang/新建文件夹",
        title: "/Users/jubaoliang/新建文件夹",
        isLeaf: false,
      },
    ];
    const next = sanitizeTree(tree);
    expect(next.map((n) => n.value)).toEqual(["/"]);
    expect(pathExistsInTree(next, "/Users/jubaoliang")).toBe(true);
  });

  it("sanitizeTree removes duplicate values anywhere in the tree", () => {
    const tree: DirTreeNode[] = [
      {
        ...root,
        children: [
          {
            value: "/Users",
            title: "Users",
            isLeaf: false,
            children: [
              {
                value: "/Users/a",
                title: "a",
                isLeaf: false,
              },
              {
                value: "/Users/a",
                title: "a-dup",
                isLeaf: false,
              },
            ],
          },
        ],
      },
    ];
    const next = sanitizeTree(tree);
    expect(next[0].children?.[0].children).toHaveLength(1);
    expect(next[0].children?.[0].children?.[0].value).toBe("/Users/a");
  });

  it("ancestorDirPaths returns parents from / down to the parent of path", () => {
    expect(ancestorDirPaths("/Users/jubaoliang/新建文件夹")).toEqual([
      "/",
      "/Users",
      "/Users/jubaoliang",
    ]);
    expect(ancestorDirPaths("/")).toEqual([]);
    expect(ancestorDirPaths("/Users")).toEqual(["/"]);
  });

  it("ancestorDirPaths can start from a home tree root", () => {
    expect(ancestorDirPaths("/home/wally/projects/app", "/home/wally")).toEqual(
      ["/home/wally", "/home/wally/projects"],
    );
    expect(ancestorDirPaths("/home/wally", "/home/wally")).toEqual([]);
  });

  it("isPathUnderHome accepts home and subdirs only", () => {
    expect(isPathUnderHome("/home/wally", "/home/wally")).toBe(true);
    expect(isPathUnderHome("/home/wally/docs", "/home/wally")).toBe(true);
    expect(isPathUnderHome("/", "/home/wally")).toBe(false);
    expect(isPathUnderHome("/tmp", "/home/wally")).toBe(false);
  });

  it("isPathUnderHome normalizes Windows separators and drive case", () => {
    expect(isPathUnderHome("C:\\Users\\Wally\\docs", "C:/Users/Wally")).toBe(
      true,
    );
    expect(isPathUnderHome("c:/Users/Wally", "C:/Users/Wally")).toBe(true);
    expect(isPathUnderHome("D:/other", "C:/Users/Wally")).toBe(false);
  });

  it("ancestorDirPaths works under a Windows drive tree root", () => {
    expect(ancestorDirPaths("C:/Users/Wally/projects/app", "C:/")).toEqual([
      "C:/",
      "C:/Users",
      "C:/Users/Wally",
      "C:/Users/Wally/projects",
    ]);
  });

  it("sanitizeTree keeps a non-/ tree root", () => {
    const homeRoot: DirTreeNode = {
      value: "/home/wally",
      title: "wally",
      isLeaf: false,
      children: [{ value: "/home/wally/docs", title: "docs", isLeaf: false }],
    };
    const next = sanitizeTree(
      [homeRoot, { value: "/home/wally/docs", title: "orphan", isLeaf: false }],
      "/home/wally",
    );
    expect(next).toHaveLength(1);
    expect(next[0].value).toBe("/home/wally");
    expect(pathExistsInTree(next, "/home/wally/docs")).toBe(true);
  });

  it("appendChildren only updates the first matching parent", () => {
    const tree: DirTreeNode[] = [
      {
        ...root,
        children: [
          {
            value: "/Users/jubaoliang",
            title: "jubaoliang",
            isLeaf: false,
          },
        ],
      },
      {
        value: "/Users/jubaoliang",
        title: "/Users/jubaoliang",
        isLeaf: false,
      },
    ];
    const next = appendChildren(tree, "/Users/jubaoliang", [
      {
        value: "/Users/jubaoliang/新建文件夹",
        title: "新建文件夹",
        isLeaf: false,
      },
    ]);
    expect(next[0].children?.[0].children?.map((c) => c.value)).toEqual([
      "/Users/jubaoliang/新建文件夹",
    ]);
    expect(next[1].children).toBeUndefined();
  });

  it("sanitizeForest keeps each volume and drops a duplicate child key", () => {
    const nodes: DirTreeNode[] = [
      {
        value: "C:/",
        title: "C:",
        isLeaf: false,
        children: [{ value: "C:/work", title: "work", isLeaf: false }],
      },
      {
        value: "D:/",
        title: "D:",
        isLeaf: false,
        children: [{ value: "D:/data", title: "data", isLeaf: false }],
      },
      { value: "C:/work", title: "orphan", isLeaf: false },
    ];
    const next = sanitizeForest(nodes, ["C:/", "D:/", "c:/"]);
    expect(next.map((node) => node.value)).toEqual(["C:/", "D:/"]);
    expect(pathExistsInTree(next, "C:/work")).toBe(true);
    expect(pathExistsInTree(next, "D:/data")).toBe(true);
  });

  it("ancestorDirPathsInForest starts at the matching volume", () => {
    expect(ancestorDirPathsInForest("D:/work/app", ["C:/", "D:/"])).toEqual([
      "D:/",
      "D:/work",
    ]);
    expect(ancestorDirPathsInForest("E:/other", ["C:/", "D:/"])).toEqual([]);
  });

  it("typed absolute paths stay fully qualified", () => {
    expect(isExplicitAbsolutePath("C:/work/data/a.txt")).toBe(true);
    expect(isExplicitAbsolutePath("D:")).toBe(false);
    expect(isExplicitAbsolutePath("D:work")).toBe(false);
    expect(commitTypedAbsolutePath("D:\\work\\")).toBe("D:/work");
    expect(commitTypedAbsolutePath("D:")).toBe("D:");
  });
});
