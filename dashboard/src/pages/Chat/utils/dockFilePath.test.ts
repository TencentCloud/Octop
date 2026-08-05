import {
  buildDockPathTree,
  canonicalizeDockFilePath,
  collectDockFolderPaths,
  dedupeDockFilePaths,
  dockFileBasename,
  dockFileTabId,
  mergeDockExpandedFolders,
  normalizeDockFilePath,
  toDockWorkspaceApiPath,
  toWorkspaceApiPath,
} from "./dockFilePath";

describe("dockFilePath", () => {
  it("normalizes file:// and backslashes", () => {
    expect(normalizeDockFilePath("file:///tmp/a.txt")).toBe("/tmp/a.txt");
    expect(normalizeDockFilePath("outbound\\report.pdf")).toBe(
      "outbound/report.pdf",
    );
  });

  it("canonicalizes agent-home and truncated .octop paths together", () => {
    expect(
      canonicalizeDockFilePath(
        "/home/wally/.octop/agents/main/generated/iron-man.pptx",
        "main",
      ),
    ).toBe("generated/iron-man.pptx");
    expect(
      canonicalizeDockFilePath(
        "/.octop/agents/main/generated/iron-man.pptx",
        "main",
      ),
    ).toBe("generated/iron-man.pptx");
    expect(
      canonicalizeDockFilePath(
        ".octop/agents/main/generated/iron-man.pptx",
        "main",
      ),
    ).toBe("generated/iron-man.pptx");
    expect(canonicalizeDockFilePath("generated/iron-man.pptx", "main")).toBe(
      "generated/iron-man.pptx",
    );
  });

  it("canonicalizes Windows agent-home paths", () => {
    expect(
      canonicalizeDockFilePath(
        "C:\\Users\\wally\\.octop\\agents\\main\\generated\\a.pptx",
        "main",
      ),
    ).toBe("generated/a.pptx");
    expect(
      canonicalizeDockFilePath(
        "C:/Users/wally/.octop/agents/main/generated/a.pptx",
        "main",
      ),
    ).toBe("generated/a.pptx");
  });

  it("dedupes absolute and relative agent paths to one entry", () => {
    expect(
      dedupeDockFilePaths(
        [
          "/.octop/agents/main/generated/iron-man.pptx",
          "/home/wally/.octop/agents/main/generated/iron-man.pptx",
          "/home/wally/.octop/agents/main/generated/ironman-ppt.js",
          "generated/ironman-ppt.py",
        ],
        "main",
      ),
    ).toEqual([
      "/home/wally/.octop/agents/main/generated/iron-man.pptx",
      "/home/wally/.octop/agents/main/generated/ironman-ppt.js",
      "generated/ironman-ppt.py",
    ]);
  });

  it("dedupes by normalized full path and keeps first-seen order", () => {
    expect(
      dedupeDockFilePaths([
        "outbound/a.txt",
        "outbound/a.txt",
        "file:///tmp/a.txt",
        "/tmp/a.txt",
        "outbound/b.txt",
      ]),
    ).toEqual(["outbound/a.txt", "/tmp/a.txt", "outbound/b.txt"]);
  });

  it("keeps host paths that contain a workspace directory segment", () => {
    expect(
      canonicalizeDockFilePath(
        "/Users/jubaoliang/workspace/sapiens_intro/Sapiens_Introduction.pptx",
        "ENG1XX",
      ),
    ).toBe(
      "/Users/jubaoliang/workspace/sapiens_intro/Sapiens_Introduction.pptx",
    );
    expect(
      toDockWorkspaceApiPath(
        "/Users/jubaoliang/workspace/sapiens_intro/Sapiens_Introduction.pptx",
        "ENG1XX",
      ),
    ).toBe(
      "file:///Users/jubaoliang/workspace/sapiens_intro/Sapiens_Introduction.pptx",
    );
  });

  it("still strips virtual /workspace/… roots", () => {
    expect(canonicalizeDockFilePath("/workspace/x.py", "main")).toBe("x.py");
    expect(canonicalizeDockFilePath("file:///workspace/x.py")).toBe("x.py");
  });

  it("toWorkspaceApiPath keeps agent-home absolute as file:// for failback", () => {
    expect(
      toWorkspaceApiPath(
        "/Users/jubaoliang/.octop/agents/SBGM5Q/earth-presentation.html",
      ),
    ).toBe(
      "file:///Users/jubaoliang/.octop/agents/SBGM5Q/earth-presentation.html",
    );
  });

  it("builds basename and tab id from normalized path", () => {
    expect(dockFileBasename("outbound/docs/note.md")).toBe("note.md");
    expect(dockFileTabId("file:///workspace/x.py")).toBe("file:x.py");
    expect(
      dockFileTabId("/home/wally/.octop/agents/main/generated/a.pptx", "main"),
    ).toBe("file:generated/a.pptx");
  });

  it("folder tree labels use full collapsed directory paths", () => {
    const tree = buildDockPathTree(
      [
        "/home/wally/.octop/agents/main/generated/iron-man.pptx",
        "/.octop/agents/main/generated/iron-man.pptx",
      ],
      "main",
    );
    expect(tree).toHaveLength(1);
    expect(tree[0].name).toBe(
      "home / wally / .octop / agents / main / generated",
    );
    expect(tree[0].path).toBe("/home/wally/.octop/agents/main/generated");
    expect(tree[0].children.map((c) => c.name)).toEqual(["iron-man.pptx"]);
  });

  it("maps download APIs; host abs stays file:// for virtual root failback", () => {
    expect(toWorkspaceApiPath("/outbound/a.txt")).toBe("outbound/a.txt");
    expect(toWorkspaceApiPath("/tmp/a.txt")).toBe("file:///tmp/a.txt");
    expect(toWorkspaceApiPath("outbound/a.txt")).toBe("outbound/a.txt");
    expect(
      toDockWorkspaceApiPath(
        "/home/wally/.octop/agents/main/generated/a.pptx",
        "main",
      ),
    ).toBe("file:///home/wally/.octop/agents/main/generated/a.pptx");
    expect(
      toDockWorkspaceApiPath(
        "C:\\Users\\wally\\.octop\\agents\\main\\generated\\a.pptx",
        "main",
      ),
    ).toBe("file:///C:/Users/wally/.octop/agents/main/generated/a.pptx");
    // Tab identity still collapses; API path does not.
    expect(
      canonicalizeDockFilePath(
        "/home/wally/.octop/agents/main/generated/a.pptx",
        "main",
      ),
    ).toBe("generated/a.pptx");
  });

  it("builds a collapsed folder tree like PR files-changed", () => {
    const tree = buildDockPathTree([
      "dashboard/src/pages/Chat/hooks/useChatDockPanel.ts",
      "dashboard/src/pages/Chat/hooks/chatStore.ts",
      "src/octop/api.md",
      "tests/unit/gateway/ws.py",
    ]);
    expect(tree).toEqual([
      {
        name: "dashboard / src / pages / Chat / hooks",
        path: "dashboard/src/pages/Chat/hooks",
        isDir: true,
        children: [
          {
            name: "chatStore.ts",
            path: "dashboard/src/pages/Chat/hooks/chatStore.ts",
            isDir: false,
            children: [],
          },
          {
            name: "useChatDockPanel.ts",
            path: "dashboard/src/pages/Chat/hooks/useChatDockPanel.ts",
            isDir: false,
            children: [],
          },
        ],
      },
      {
        name: "src / octop",
        path: "src/octop",
        isDir: true,
        children: [
          {
            name: "api.md",
            path: "src/octop/api.md",
            isDir: false,
            children: [],
          },
        ],
      },
      {
        name: "tests / unit / gateway",
        path: "tests/unit/gateway",
        isDir: true,
        children: [
          {
            name: "ws.py",
            path: "tests/unit/gateway/ws.py",
            isDir: false,
            children: [],
          },
        ],
      },
    ]);
  });

  it("merges expanded folders without reopening user-collapsed dirs", () => {
    const first = buildDockPathTree(["a/b/one.txt"]);
    const folders1 = collectDockFolderPaths(first);
    const initial = mergeDockExpandedFolders([], folders1, []);
    expect([...initial.expanded]).toEqual(["a/b"]);

    const collapsed = new Set<string>(); // user collapsed a/b
    const second = buildDockPathTree(["a/b/one.txt", "c/d/two.txt"]);
    const folders2 = collectDockFolderPaths(second);
    const merged = mergeDockExpandedFolders(collapsed, folders2, initial.seen);
    expect(merged.expanded.has("a/b")).toBe(false);
    expect(merged.expanded.has("c/d")).toBe(true);
  });
});
