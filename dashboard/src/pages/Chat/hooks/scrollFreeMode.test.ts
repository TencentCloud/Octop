import { describe, expect, it } from "vitest";
import { shouldEnterFreeModeOnScrollUp } from "./scrollFreeMode";

describe("shouldEnterFreeModeOnScrollUp", () => {
  it("ignores tiny dips while still near the bottom (Safari reflow)", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({ upDelta: 2, atBottom: true, gapToBottom: 2 }),
    ).toBe(false);
  });

  it("leaves follow on intentional upward scroll even near the bottom", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({
        upDelta: 20,
        atBottom: true,
        gapToBottom: 20,
      }),
    ).toBe(true);
  });

  it("always leaves follow once outside the bottom sticky zone", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({
        upDelta: 3,
        atBottom: false,
        gapToBottom: 300,
      }),
    ).toBe(true);
  });

  it("ignores non-upward movement", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({
        upDelta: 0,
        atBottom: false,
        gapToBottom: 300,
      }),
    ).toBe(false);
  });

  it("stays in follow when a layout clamp lands exactly at the bottom", () => {
    // Closing the file dock grows the viewport; the browser rewrites scrollTop
    // to the new max. The *resulting* gap is ~0, so this is not user intent.
    expect(
      shouldEnterFreeModeOnScrollUp({
        upDelta: 200,
        atBottom: true,
        gapToBottom: 0,
      }),
    ).toBe(false);
  });

  it("leaves follow when the scroll-up genuinely moves away from the bottom", () => {
    expect(
      shouldEnterFreeModeOnScrollUp({
        upDelta: 30,
        atBottom: false,
        gapToBottom: 120,
      }),
    ).toBe(true);
  });
});
