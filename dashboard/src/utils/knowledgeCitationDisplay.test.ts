import { describe, expect, it } from "vitest";

import {
  knowledgeCitationDirectory,
  knowledgeCitationHasNestedPath,
  knowledgeCitationHref,
  knowledgeCitationTooltip,
} from "./knowledgeCitationDisplay";

describe("knowledgeCitationDisplay", () => {
  it("builds deep link", () => {
    expect(
      knowledgeCitationHref({
        kbId: "kb1",
        kbName: "Docs",
        docId: "d1",
        filename: "a.md",
        path: "notes/a.md",
      }),
    ).toBe("/knowledge-bases?kb=kb1&doc=d1");
  });

  it("tooltip includes kb and path when present", () => {
    expect(
      knowledgeCitationTooltip({
        kbId: "kb1",
        kbName: "Docs",
        docId: "d1",
        filename: "a.md",
        path: "notes/a.md",
      }),
    ).toBe("Docs · notes/a.md");
  });

  it("tooltip without path uses filename", () => {
    expect(
      knowledgeCitationTooltip({
        kbId: "kb1",
        kbName: "Docs",
        docId: "d1",
        filename: "a.md",
      }),
    ).toBe("Docs · a.md");
  });

  it("directory is parent of path", () => {
    expect(knowledgeCitationDirectory("notes/a.md")).toBe("notes");
    expect(knowledgeCitationDirectory("a.md")).toBe("");
  });

  it("nested path flag is only true with a parent directory", () => {
    expect(
      knowledgeCitationHasNestedPath({
        kbId: "kb1",
        kbName: "Docs",
        docId: "d1",
        filename: "a.md",
        path: "notes/a.md",
      }),
    ).toBe(true);
    expect(
      knowledgeCitationHasNestedPath({
        kbId: "kb1",
        kbName: "Docs",
        docId: "d1",
        filename: "a.md",
        path: "a.md",
      }),
    ).toBe(false);
    expect(
      knowledgeCitationHasNestedPath({
        kbId: "kb1",
        kbName: "Docs",
        docId: "d1",
        filename: "a.md",
      }),
    ).toBe(false);
  });
});
