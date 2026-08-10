import { describe, expect, it } from "vitest";
import { resolveTurnModelOverride, resolveTurnModelRef } from "./chatMessages";

describe("resolveTurnModelRef", () => {
  it("sends only an explicit composer selection", () => {
    expect(resolveTurnModelRef("p/picked")).toBe("p/picked");
  });

  it("omits model when composer is Auto so backend can resolve expert default", () => {
    expect(resolveTurnModelRef(null)).toBeNull();
    expect(resolveTurnModelRef("")).toBeNull();
  });
});

describe("resolveTurnModelOverride", () => {
  it("treats matching expert default as no override chip", () => {
    expect(resolveTurnModelOverride("p/default", "p/default")).toBeNull();
  });
});
