import { describe, expect, it } from "vitest";

import {
  insertScriptPathChildren,
  scriptPathAncestors,
  scriptPathFromTree,
  scriptPathNodes,
} from "./scriptPathTree";

describe("scriptPathTree", () => {
  it("keeps a workspace-relative path and drops a leading slash", () => {
    expect(scriptPathFromTree("/scripts/daily.py")).toBe("scripts/daily.py");
    expect(scriptPathFromTree("scripts\\daily.py")).toBe("scripts/daily.py");
  });

  it("lets the user pick files and only expand directories", () => {
    const nodes = scriptPathNodes([
      { path: "/scripts", is_dir: true },
      { path: "/daily.py", is_dir: false },
      { path: "/README.md", is_dir: false },
      { path: "/notes.txt", is_dir: false },
      { path: "/.octop", is_dir: true },
    ]);
    expect(nodes.map((node) => node.value)).toEqual([
      "dir:scripts",
      "daily.py",
    ]);
    expect(nodes[0]?.selectable).toBe(false);
    expect(nodes[1]?.label).toBe("daily.py");
    expect(nodes[1]?.selectable).toBe(true);
  });

  it("hides files that do not match the selected language", () => {
    const nodes = scriptPathNodes(
      [
        { path: "job.py", is_dir: false },
        { path: "job.sh", is_dir: false },
        { path: "job.ps1", is_dir: false },
      ],
      "bash",
    );
    expect(nodes.map((node) => node.value)).toEqual(["job.sh"]);
  });

  it("loads parent directories for a saved path", () => {
    expect(scriptPathAncestors("/scripts/nightly/job.py")).toEqual([
      "",
      "scripts",
      "scripts/nightly",
    ]);
  });

  it("attaches a directory listing under that directory", () => {
    const root = scriptPathNodes([{ path: "scripts", is_dir: true }]);
    const next = insertScriptPathChildren(root, "scripts", [
      {
        title: "job.py",
        label: "scripts/job.py",
        value: "scripts/job.py",
        selectable: true,
        isLeaf: true,
      },
    ]);
    expect(next[0]?.children?.[0]?.value).toBe("scripts/job.py");
  });
});
