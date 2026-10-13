import { describe, expect, it } from "vitest";

import { effectiveDocumentLimit } from "./documentLimit";

describe("documentLimit", () => {
  it("treats zero as an unlimited document limit", () => {
    expect(effectiveDocumentLimit(0, 100)).toBe(Number.POSITIVE_INFINITY);
    expect(effectiveDocumentLimit(undefined, 0)).toBe(Number.POSITIVE_INFINITY);
    expect(effectiveDocumentLimit(undefined, 100)).toBe(100);
    expect(effectiveDocumentLimit(7, 100)).toBe(7);
  });
});
