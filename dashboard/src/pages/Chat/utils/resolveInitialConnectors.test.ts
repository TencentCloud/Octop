import { describe, expect, it } from "vitest";

import { resolveInitialConnectors } from "./resolveInitialConnectors";

describe("resolveInitialConnectors", () => {
  const allowed = new Set(["a", "b", "c"]);

  it("keeps current session selection (including opt-out of defaults)", () => {
    expect(
      resolveInitialConnectors({
        prev: ["b"],
        saved: ["a"],
        hasSaved: true,
        defaults: ["a", "c"],
        allowed,
      }),
    ).toEqual(["b"]);
  });

  it("uses defaults when nothing saved yet", () => {
    expect(
      resolveInitialConnectors({
        prev: [],
        saved: [],
        hasSaved: false,
        defaults: ["a", "c"],
        allowed,
      }),
    ).toEqual(["a", "c"]);
  });

  it("respects saved preference including empty opt-out", () => {
    expect(
      resolveInitialConnectors({
        prev: [],
        saved: [],
        hasSaved: true,
        defaults: ["a"],
        allowed,
      }),
    ).toEqual([]);
    expect(
      resolveInitialConnectors({
        prev: [],
        saved: ["b"],
        hasSaved: true,
        defaults: ["a"],
        allowed,
      }),
    ).toEqual(["b"]);
  });

  it("filters unavailable names", () => {
    expect(
      resolveInitialConnectors({
        prev: [],
        saved: ["gone", "b"],
        hasSaved: true,
        defaults: ["a"],
        allowed,
      }),
    ).toEqual(["b"]);
  });
});
