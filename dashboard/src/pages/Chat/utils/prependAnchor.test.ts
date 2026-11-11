import { describe, expect, it } from "vitest";
import { prependAnchorShift } from "./prependAnchor";

function groups(ids: string[][]) {
  return ids.map((messageIds) => ({
    messages: messageIds.map((id) => ({ id })),
  }));
}

describe("prependAnchorShift", () => {
  it("counts only groups inserted before the anchor", () => {
    const shift = prependAnchorShift(
      groups([["old-a"], ["old-b"], ["anchor"], ["sent-now"]]),
      "anchor",
    );
    expect(shift).toEqual({ prependedGroups: 2, mergedIntoFirst: false });
  });

  it("does not treat a message appended during the load as a prepend", () => {
    const shift = prependAnchorShift(
      groups([["anchor"], ["sent-now"]]),
      "anchor",
    );
    expect(shift).toEqual({ prependedGroups: 0, mergedIntoFirst: false });
  });

  it("notices when older rows merge into the anchored group", () => {
    const shift = prependAnchorShift(
      groups([["older", "anchor"], ["sent-now"]]),
      "anchor",
    );
    expect(shift).toEqual({ prependedGroups: 0, mergedIntoFirst: true });
  });
});
