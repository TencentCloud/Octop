import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import GitDiffView, { parseUnifiedDiff } from "./GitDiffView";

const SAMPLE = [
  "diff --git a/README.md b/README.md",
  "index 0ebfc39..1a2b3c4 100644",
  "--- a/README.md",
  "+++ b/README.md",
  "@@ -41,3 +41,5 @@ section",
  " ```bash",
  " pnpm build",
  " ```",
  "+",
  "+## E2E demo note",
  "-old line",
  "\\ No newline at end of file",
].join("\n");

describe("parseUnifiedDiff", () => {
  it("classifies meta, hunk, add, del and ctx rows with line numbers", () => {
    const rows = parseUnifiedDiff(SAMPLE);
    expect(rows[0].kind).toBe("meta");
    const hunk = rows.find((r) => r.kind === "hunk");
    expect(hunk?.text).toContain("@@ -41,3 +41,5 @@");

    const adds = rows.filter((r) => r.kind === "add");
    expect(adds.map((r) => r.text)).toEqual(["+", "+## E2E demo note"]);
    expect(adds[0].newNo).toBe(44);
    expect(adds[0].oldNo).toBeNull();

    const dels = rows.filter((r) => r.kind === "del");
    expect(dels.map((r) => r.text)).toEqual(["-old line"]);
    expect(dels[0].oldNo).toBe(44);
    expect(dels[0].newNo).toBeNull();

    const ctx = rows.filter((r) => r.kind === "ctx");
    expect(ctx).toHaveLength(3);
    expect(ctx[0].oldNo).toBe(41);
    expect(ctx[0].newNo).toBe(41);

    expect(rows.some((r) => r.kind === "meta" && r.text.startsWith("\\"))).toBe(
      true,
    );
  });

  it("returns no rows for empty input", () => {
    expect(parseUnifiedDiff("")).toEqual([]);
  });
});

describe("GitDiffView", () => {
  it("renders added and removed lines", () => {
    render(<GitDiffView diff={SAMPLE} />);
    expect(screen.getByText("+## E2E demo note")).toBeInTheDocument();
    expect(screen.getByText("-old line")).toBeInTheDocument();
    expect(screen.getByText("@@ -41,3 +41,5 @@ section")).toBeInTheDocument();
  });

  it("shows the empty state for identical content", () => {
    render(<GitDiffView diff="" />);
    expect(screen.getByText("没有差异")).toBeInTheDocument();
  });

  it("warns when the diff was truncated", () => {
    render(<GitDiffView diff={SAMPLE} truncated />);
    expect(screen.getByText("差异过大，已截断显示")).toBeInTheDocument();
  });
});
