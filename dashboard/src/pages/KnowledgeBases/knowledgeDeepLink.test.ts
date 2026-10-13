import { describe, expect, it } from "vitest";

import { resolveKnowledgeDeepLink } from "./knowledgeDeepLink";

describe("resolveKnowledgeDeepLink", () => {
  it("resolves nested doc folder", () => {
    const r = resolveKnowledgeDeepLink({
      kb: "kb1",
      doc: "d1",
      bases: [{ id: "kb1" }],
      documents: [{ id: "d1", filename: "a.md", path: "notes/a.md" }],
    });
    expect(r).toEqual({
      kbId: "kb1",
      document: expect.objectContaining({ id: "d1" }),
      folder: "notes",
    });
  });

  it("resolves root documents to empty folder", () => {
    const r = resolveKnowledgeDeepLink({
      kb: "kb1",
      doc: "d1",
      bases: [{ id: "kb1" }],
      documents: [{ id: "d1", filename: "a.md", path: "a.md" }],
    });
    expect(r?.folder).toBe("");
  });

  it("returns null when kb or doc is missing", () => {
    expect(
      resolveKnowledgeDeepLink({
        kb: "missing",
        doc: "d1",
        bases: [{ id: "kb1" }],
        documents: [{ id: "d1", filename: "a.md" }],
      }),
    ).toBeNull();
  });
});
