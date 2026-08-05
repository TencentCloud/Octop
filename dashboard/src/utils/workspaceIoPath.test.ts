import { describe, expect, it } from "vitest";
import {
  isHostAbsolutePath,
  stripVirtualWorkspaceRoot,
  toDockWorkspaceApiPath,
  toWorkspaceApiPath,
} from "./workspaceIoPath";

describe("workspaceIoPath", () => {
  it("detects host abs vs outbound keys", () => {
    expect(isHostAbsolutePath("/Users/me/a.html")).toBe(true);
    expect(isHostAbsolutePath("file:///tmp/x")).toBe(true);
    expect(isHostAbsolutePath("/outbound/a.png")).toBe(false);
    expect(isHostAbsolutePath("outbound/a.png")).toBe(false);
    expect(isHostAbsolutePath("generated/a.html")).toBe(false);
  });

  it("strips only virtual /workspace/ prefix", () => {
    expect(stripVirtualWorkspaceRoot("/workspace/x.py")).toBe("x.py");
    expect(stripVirtualWorkspaceRoot("/workspace")).toBe("");
    expect(
      stripVirtualWorkspaceRoot(
        "/Users/jubaoliang/workspace/sapiens_intro/a.pptx",
      ),
    ).toBe("/Users/jubaoliang/workspace/sapiens_intro/a.pptx");
  });

  it("keeps agent-home absolute as file:// for BackendWorkspace failback", () => {
    const abs =
      "/Users/jubaoliang/.octop/agents/SBGM5Q/earth-presentation.html";
    expect(toWorkspaceApiPath(abs)).toBe(`file://${abs}`);
    expect(toDockWorkspaceApiPath(abs)).toBe(`file://${abs}`);
    expect(
      toDockWorkspaceApiPath("/home/wally/.octop/agents/main/generated/a.pptx"),
    ).toBe("file:///home/wally/.octop/agents/main/generated/a.pptx");
  });

  it("rewrites legacy /outbound to relative", () => {
    expect(toWorkspaceApiPath("/outbound/a.txt")).toBe("outbound/a.txt");
    expect(toDockWorkspaceApiPath("/outbound/a.txt")).toBe("outbound/a.txt");
  });
});
