import { afterEach, describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import {
  KEYBOARD_GAP_THRESHOLD_PX,
  measureKeyboardOffset,
  useKeyboardOffset,
} from "./useKeyboardOffset";

describe("measureKeyboardOffset", () => {
  it("ignores home-indicator-sized leftover as a closed keyboard", () => {
    expect(
      measureKeyboardOffset(844, { height: 810, offsetTop: 0 }),
    ).toBe(0);
    expect(
      measureKeyboardOffset(844, {
        height: 844 - KEYBOARD_GAP_THRESHOLD_PX,
        offsetTop: 0,
      }),
    ).toBe(0);
  });

  it("reports a real soft keyboard", () => {
    expect(
      measureKeyboardOffset(844, { height: 500, offsetTop: 0 }),
    ).toBe(344);
  });

  it("subtracts visualViewport.offsetTop before comparing", () => {
    expect(
      measureKeyboardOffset(844, { height: 500, offsetTop: 40 }),
    ).toBe(304);
  });
});

describe("useKeyboardOffset", () => {
  const originalMatchMedia = window.matchMedia;
  const originalVisualViewport = window.visualViewport;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      value: originalVisualViewport,
    });
    document.documentElement.style.removeProperty("--keyboard-offset");
  });

  it("does not set --keyboard-offset outside PWA standalone", () => {
    window.matchMedia = ((query: string) =>
      ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
      })) as typeof window.matchMedia;

    renderHook(() => useKeyboardOffset());

    expect(
      document.documentElement.style.getPropertyValue("--keyboard-offset"),
    ).toBe("");
  });
});
