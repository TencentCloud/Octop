import { describe, expect, it } from "vitest";

import { withDefaultOpenKnowledgeBases } from "./withDefaultOpenKnowledgeBases";

describe("withDefaultOpenKnowledgeBases", () => {
  it("adds default_open knowledge bases to the selection", () => {
    expect(withDefaultOpenKnowledgeBases(["kb-b"], ["kb-a", "kb-c"])).toEqual([
      "kb-b",
      "kb-a",
      "kb-c",
    ]);
  });

  it("does not duplicate selected defaults", () => {
    expect(withDefaultOpenKnowledgeBases(["kb-a", "kb-b"], ["kb-a"])).toEqual([
      "kb-a",
      "kb-b",
    ]);
  });
});
