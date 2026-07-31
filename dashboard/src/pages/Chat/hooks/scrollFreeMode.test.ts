import { describe, expect, it } from "vitest";
import { shouldEnterFreeModeOnScrollUp } from "./scrollFreeMode";

describe("shouldEnterFreeModeOnScrollUp", () => {
  it("ignores tiny dips while still near the bottom (Safari reflow)", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({ upDelta: 2, atBottom: true }),
    ).toBe(false);
  });

  it("leaves follow on intentional upward scroll even near the bottom", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({ upDelta: 20, atBottom: true }),
    ).toBe(true);
  });

  it("always leaves follow once outside the bottom sticky zone", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({ upDelta: 3, atBottom: false }),
    ).toBe(true);
  });

  it("ignores non-upward movement", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({ upDelta: 0, atBottom: false }),
    ).toBe(false);
  });
});
