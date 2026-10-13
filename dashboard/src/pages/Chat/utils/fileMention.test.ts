import { describe, expect, it } from "vitest";
import { getMentionAtCursor } from "./mentionAtCursor";
import {
  isPathLikeMentionQuery,
  isSkippedWorkspacePath,
  normalizeWorkspaceRelPath,
  rankWorkspaceMentionFiles,
  replaceFileMentionQuery,
  shouldSearchWorkspaceMentions,
  workspaceFileShortName,
  workspaceGlobPattern,
  workspaceMentionHintState,
} from "./fileMention";

describe("workspace file mention helpers", () => {
  it("normalizes to a workspace-relative path and uses the basename as the label", () => {
    expect(normalizeWorkspaceRelPath("/docs/api.md")).toBe("docs/api.md");
    expect(workspaceFileShortName("/docs/api.md")).toBe("api.md");
    expect(workspaceFileShortName("SOUL.md")).toBe("SOUL.md");
  });

  it("skips system and dependency trees", () => {
    expect(isSkippedWorkspacePath(".octop/auth/token")).toBe(true);
    expect(isSkippedWorkspacePath("node_modules/pkg/index.js")).toBe(true);
    expect(isSkippedWorkspacePath("docs/api.md")).toBe(false);
    expect(isSkippedWorkspacePath("inbound/shot.png")).toBe(true);
    expect(isSkippedWorkspacePath("outbound/note.md")).toBe(true);
  });

  it("does not search on empty @ or a single character", () => {
    expect(shouldSearchWorkspaceMentions("")).toBe(false);
    expect(shouldSearchWorkspaceMentions("  ")).toBe(false);
    expect(shouldSearchWorkspaceMentions("s")).toBe(false);
    expect(shouldSearchWorkspaceMentions("so")).toBe(true);
    expect(shouldSearchWorkspaceMentions("soul")).toBe(true);
  });

  it("treats path-shaped queries as file-first", () => {
    expect(isPathLikeMentionQuery("soul")).toBe(false);
    expect(isPathLikeMentionQuery("api.md")).toBe(true);
    expect(isPathLikeMentionQuery("docs/a")).toBe(true);
  });

  it("picks the placeholder hint without treating it as a search", () => {
    expect(
      workspaceMentionHintState({
        query: "",
        loading: false,
        error: null,
        fileCount: 0,
      }),
    ).toBe("typeToSearch");
    expect(
      workspaceMentionHintState({
        query: "s",
        loading: false,
        error: null,
        fileCount: 0,
      }),
    ).toBe("typeMore");
    expect(
      workspaceMentionHintState({
        query: "so",
        loading: true,
        error: null,
        fileCount: 0,
      }),
    ).toBe("searching");
  });

  it("builds a glob around the typed fragment", () => {
    expect(workspaceGlobPattern("soul")).toBe("**/*soul*");
    expect(workspaceGlobPattern("docs/api")).toBe("**/docs/api*");
    expect(workspaceGlobPattern("foo*bar")).toBe("**/*foo\\*bar*");
  });

  it("ranks basename hits first and keeps the relative full path", () => {
    const ranked = rankWorkspaceMentionFiles(
      [
        { path: "/docs/other.md" },
        { path: "/docs/SOUL.md" },
        { path: "/SOUL.md" },
        { path: "/.octop/SOUL.md", is_dir: false },
        { path: "/inbound/soul.png", is_dir: false },
        { path: "/skills", is_dir: true },
      ],
      "soul",
    );
    expect(ranked.map((item) => item.path)).toEqual([
      "SOUL.md",
      "docs/SOUL.md",
    ]);
    expect(ranked[0]?.label).toBe("SOUL.md");
  });
});

describe("replaceFileMentionQuery", () => {
  it("inserts @workspace/rel/path and keeps spaces in the filename", () => {
    expect(replaceFileMentionQuery("@api", 0, "api", "docs/api.md")).toEqual({
      text: "@docs/api.md ",
      cursor: 13,
    });
    expect(
      replaceFileMentionQuery("请看 @note", 3, "note", "notes/my file.md"),
    ).toEqual({
      text: "请看 @notes/my file.md ",
      cursor: 21,
    });
  });

  it("does not toggle an already-inserted path out of the draft", () => {
    expect(
      replaceFileMentionQuery("@docs/api.md @api", 13, "api", "docs/api.md"),
    ).toEqual({
      text: "@docs/api.md @docs/api.md ",
      cursor: 26,
    });
  });
});

describe("getMentionAtCursor with file queries", () => {
  it("keeps path separators inside the @ query", () => {
    expect(getMentionAtCursor("@docs/api")).toEqual({
      query: "docs/api",
      atIndex: 0,
    });
  });
});
