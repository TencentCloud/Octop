import { describe, expect, it } from "vitest";

import { withDefaultOpenConnectors } from "./withDefaultOpenConnectors";

describe("withDefaultOpenConnectors", () => {
  it("forces default_open names back into the selection", () => {
    expect(withDefaultOpenConnectors(["b"], ["a", "c"])).toEqual([
      "b",
      "a",
      "c",
    ]);
  });

  it("dedupes existing defaults", () => {
    expect(withDefaultOpenConnectors(["a", "b"], ["a"])).toEqual(["a", "b"]);
  });

  it("returns defaults when selection empty", () => {
    expect(withDefaultOpenConnectors([], ["a"])).toEqual(["a"]);
  });
});
