import { describe, expect, it } from "vitest";
import { createDetailRequestGate } from "./detailRequestGate";

describe("createDetailRequestGate", () => {
  it("accepts only the most recent detail request", () => {
    const gate = createDetailRequestGate();
    const first = gate.begin();
    const second = gate.begin();

    expect(gate.isCurrent(first)).toBe(false);
    expect(gate.isCurrent(second)).toBe(true);
  });
});
