import { describe, expect, it } from "vitest";
import { turnStatusAction } from "./turnStatusGate";

describe("turnStatusAction", () => {
  it("expects stream when active", () => {
    expect(turnStatusAction(true)).toBe("expect_stream");
  });

  it("stays idle when inactive", () => {
    expect(turnStatusAction(false)).toBe("idle");
  });
});
