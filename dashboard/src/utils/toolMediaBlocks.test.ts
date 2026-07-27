import { describe, expect, it } from "vitest";
import {
  canonicalizeMediaApiUrl,
  isHostAbsoluteMediaPath,
  workspaceDownloadUrl,
} from "./toolMediaBlocks";

describe("workspaceDownloadUrl", () => {
  it("keeps host-absolute paths as-is", () => {
    const url = workspaceDownloadUrl("main", "/Users/me/Desktop/a.pptx");
    expect(url).toContain("path=%2FUsers%2Fme%2FDesktop%2Fa.pptx");
  });

  it("rewrites legacy /outbound/… to relative workspace keys", () => {
    const url = workspaceDownloadUrl("main", "/outbound/chart.png");
    expect(url).toContain("path=outbound%2Fchart.png");
    expect(url).not.toContain("path=%2Foutbound");
  });

  it("passes relative outbound without adding a slash", () => {
    const url = workspaceDownloadUrl("main", "outbound/chart.png");
    expect(url).toContain("path=outbound%2Fchart.png");
  });
});

describe("canonicalizeMediaApiUrl", () => {
  it("rewrites stored download links with /outbound/ path", () => {
    const raw =
      "/api/agents/main/workspace/download?path=%2Foutbound%2Fchart.png";
    const next = canonicalizeMediaApiUrl(raw);
    expect(next).toContain("path=outbound%2Fchart.png");
    expect(next).not.toContain("path=%2Foutbound");
  });
});

describe("isHostAbsoluteMediaPath", () => {
  it("treats /outbound as workspace key, not host abs", () => {
    expect(isHostAbsoluteMediaPath("/outbound/a.png")).toBe(false);
    expect(isHostAbsoluteMediaPath("/Users/me/a.png")).toBe(true);
  });
});
