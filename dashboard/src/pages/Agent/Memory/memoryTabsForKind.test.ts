import { describe, expect, it } from "vitest";
import { memoryTabsForKind } from "./MemoryPanel";

describe("memoryTabsForKind", () => {
  it("keeps the full memory dashboard for a managed expert", () => {
    const keys = memoryTabsForKind("managed").map((tab) => tab.key);
    expect(keys).toContain("settings");
    expect(keys).toContain("conversations");
    expect(keys.length).toBeGreaterThan(1);
  });

  it("keeps the full memory dashboard for other experts", () => {
    const keys = memoryTabsForKind("expert").map((tab) => tab.key);
    expect(keys).toContain("overview");
    expect(keys).toContain("conversations");
    expect(keys.length).toBeGreaterThan(1);
  });
});
