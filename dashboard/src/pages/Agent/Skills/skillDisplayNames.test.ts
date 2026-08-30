import { describe, expect, it } from "vitest";
import { resolveSkillDisplayName } from "./skillDisplayNames";

describe("resolveSkillDisplayName", () => {
  it("prefers the API presentation name over the slug", () => {
    expect(
      resolveSkillDisplayName({ slug: "pdf", name: "PDF 阅读与编辑" }),
    ).toBe("PDF 阅读与编辑");
  });

  it("uses the slug when the API only returns the identity name", () => {
    expect(resolveSkillDisplayName({ slug: "pdf", name: "pdf" })).toBe("pdf");
  });
});
