import { describe, expect, it } from "vitest";

import {
  isKnowledgeDocumentLimitReached,
  knowledgeDocumentCap,
} from "./knowledgeLimits";

describe("knowledgeDocumentCap", () => {
  it("treats 0 as unlimited", () => {
    expect(knowledgeDocumentCap(0, 100)).toBeNull();
    expect(isKnowledgeDocumentLimitReached(0, null)).toBe(false);
    expect(isKnowledgeDocumentLimitReached(500, null)).toBe(false);
  });

  it("uses a positive per-base cap", () => {
    expect(knowledgeDocumentCap(2, 100)).toBe(2);
    expect(isKnowledgeDocumentLimitReached(1, 2)).toBe(false);
    expect(isKnowledgeDocumentLimitReached(2, 2)).toBe(true);
  });

  it("falls back when the base has no cap", () => {
    expect(knowledgeDocumentCap(undefined, 100)).toBe(100);
    expect(knowledgeDocumentCap(null, 100)).toBe(100);
  });
});
