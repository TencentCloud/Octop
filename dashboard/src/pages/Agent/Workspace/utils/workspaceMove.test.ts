import { describe, expect, it } from "vitest";
import { parentDir, resolveWorkspaceMoveDest } from "./workspaceMove";

describe("resolveWorkspaceMoveDest", () => {
  it("moves a file into a folder when dropped onto it", () => {
    expect(
      resolveWorkspaceMoveDest({
        dragPath: "/docs/a.md",
        dropPath: "/notes",
        dropIsDir: true,
        dropToGap: false,
      }),
    ).toBe("/notes/a.md");
  });

  it("moves a file into the parent when dropped in a gap next to a folder", () => {
    expect(
      resolveWorkspaceMoveDest({
        dragPath: "/docs/a.md",
        dropPath: "/notes",
        dropIsDir: true,
        dropToGap: true,
      }),
    ).toBe("/a.md");
  });

  it("moves a file into the same folder as another file", () => {
    expect(
      resolveWorkspaceMoveDest({
        dragPath: "/docs/a.md",
        dropPath: "/notes/b.md",
        dropIsDir: false,
        dropToGap: false,
      }),
    ).toBe("/notes/a.md");
  });

  it("rejects dropping a folder into itself", () => {
    expect(
      resolveWorkspaceMoveDest({
        dragPath: "/docs",
        dropPath: "/docs/nested",
        dropIsDir: true,
        dropToGap: false,
      }),
    ).toBeNull();
  });

  it("returns null when the destination is unchanged", () => {
    expect(
      resolveWorkspaceMoveDest({
        dragPath: "/docs/a.md",
        dropPath: "/docs/b.md",
        dropIsDir: false,
        dropToGap: true,
      }),
    ).toBeNull();
  });
});

describe("parentDir", () => {
  it("returns workspace root for top-level paths", () => {
    expect(parentDir("/docs")).toBe("/");
    expect(parentDir("/docs/a.md")).toBe("/docs");
  });
});
