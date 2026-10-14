import { describe, expect, it } from "vitest";
import {
  applyListOrder,
  applyManualOrder,
  groupSequence,
  joinSequence,
  mergeOrder,
  moveIdBy,
  moveIdTo,
  parseListOrder,
  togglePinned,
} from "./listOrder";

describe("parseListOrder", () => {
  it("returns empty state for null / garbage / wrong shapes", () => {
    expect(parseListOrder(null)).toEqual({ pinned: [], order: [] });
    expect(parseListOrder("{not-json")).toEqual({ pinned: [], order: [] });
    expect(parseListOrder("[1,2]")).toEqual({ pinned: [], order: [] });
    expect(parseListOrder('"str"')).toEqual({ pinned: [], order: [] });
    expect(parseListOrder("{}")).toEqual({ pinned: [], order: [] });
  });

  it("drops non-string, empty and duplicate ids", () => {
    const raw = JSON.stringify({
      pinned: ["a", 1, "", "a", "b"],
      order: ["x", null, "x", "y"],
    });
    expect(parseListOrder(raw)).toEqual({
      pinned: ["a", "b"],
      order: ["x", "y"],
    });
  });
});

describe("mergeOrder", () => {
  it("keeps known ids in manual sequence and appends new ones", () => {
    expect(mergeOrder(["c", "a", "gone"], ["a", "b", "c"])).toEqual([
      "c",
      "a",
      "b",
    ]);
  });

  it("returns incoming order when nothing known survives", () => {
    expect(mergeOrder([], ["a", "b"])).toEqual(["a", "b"]);
    expect(mergeOrder(["gone"], ["a"])).toEqual(["a"]);
  });
});

describe("applyManualOrder", () => {
  const defaults = [
    { id: "a" },
    { id: "b" },
    { id: "c" },
  ];
  const getId = (x: { id: string }) => x.id;

  it("falls back to default order when no manual order exists", () => {
    expect(applyManualOrder(defaults, [], getId).map(getId)).toEqual([
      "a",
      "b",
      "c",
    ]);
  });

  it("applies the manual sequence and appends un-ordered items", () => {
    expect(applyManualOrder(defaults, ["c", "a"], getId).map(getId)).toEqual([
      "c",
      "a",
      "b",
    ]);
  });

  it("ignores ids that no longer exist", () => {
    expect(
      applyManualOrder(defaults, ["gone", "b"], getId).map(getId),
    ).toEqual(["b", "a", "c"]);
  });
});

describe("applyListOrder", () => {
  const defaults = [{ id: "a" }, { id: "b" }, { id: "c" }];
  const getId = (x: { id: string }) => x.id;

  it("renders pinned items first, then the manual order", () => {
    const state = { pinned: ["c"], order: ["b", "c", "a"] };
    expect(applyListOrder(defaults, state, getId).map(getId)).toEqual([
      "c",
      "b",
      "a",
    ]);
  });

  it("keeps pinned items in their order-sequence relative to each other", () => {
    const state = { pinned: ["a", "c"], order: ["c", "a", "b"] };
    expect(applyListOrder(defaults, state, getId).map(getId)).toEqual([
      "c",
      "a",
      "b",
    ]);
  });

  it("handles empty / null state as pure default order", () => {
    expect(applyListOrder(defaults, null, getId).map(getId)).toEqual([
      "a",
      "b",
      "c",
    ]);
  });
});

describe("togglePinned", () => {
  it("adds and removes ids", () => {
    expect(togglePinned([], "a")).toEqual(["a"]);
    expect(togglePinned(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("groupSequence / joinSequence", () => {
  it("splits and rejoins without losing order", () => {
    const groups = groupSequence(["p1", "x", "p2", "y"], new Set(["p1", "p2"]));
    expect(groups).toEqual({ pinnedSeq: ["p1", "p2"], restSeq: ["x", "y"] });
    expect(joinSequence(groups)).toEqual(["p1", "p2", "x", "y"]);
  });
});

describe("moveIdBy / moveIdTo", () => {
  it("moves within bounds and returns null out of bounds", () => {
    expect(moveIdBy(["a", "b", "c"], "a", 1)).toEqual(["b", "a", "c"]);
    expect(moveIdBy(["a", "b", "c"], "c", -1)).toEqual(["a", "c", "b"]);
    expect(moveIdBy(["a", "b", "c"], "a", -1)).toBeNull();
    expect(moveIdBy(["a", "b", "c"], "c", 1)).toBeNull();
    expect(moveIdBy(["a", "b"], "zz", 1)).toBeNull();
  });

  it("relocates before/after a target id", () => {
    expect(moveIdTo(["a", "b", "c"], "a", "c", "after")).toEqual([
      "b",
      "c",
      "a",
    ]);
    expect(moveIdTo(["a", "b", "c"], "c", "a", "before")).toEqual([
      "c",
      "a",
      "b",
    ]);
    expect(moveIdTo(["a", "b", "c"], "a", "a", "before")).toBeNull();
    expect(moveIdTo(["a", "b"], "a", "zz", "before")).toBeNull();
  });
});
