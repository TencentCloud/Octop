import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import {
  KEYBOARD_GAP_THRESHOLD_PX,
  measureKeyboardOffset,
  measureLayoutHeight,
  useKeyboardOffset,
} from "./useKeyboardOffset";

describe("measureKeyboardOffset", () => {
  it("ignores home-indicator-sized leftover as a closed keyboard", () => {
    expect(measureKeyboardOffset(844, { height: 810, offsetTop: 0 })).toBe(0);
    expect(
      measureKeyboardOffset(844, {
        height: 844 - KEYBOARD_GAP_THRESHOLD_PX,
        offsetTop: 0,
      }),
    ).toBe(0);
  });

  it("reports a real soft keyboard", () => {
    expect(measureKeyboardOffset(844, { height: 500, offsetTop: 0 })).toBe(344);
  });

  it("subtracts visualViewport.offsetTop before comparing", () => {
    expect(measureKeyboardOffset(844, { height: 500, offsetTop: 40 })).toBe(
      304,
    );
  });
});

describe("measureLayoutHeight", () => {
  it("prefers the larger of clientHeight and innerHeight", () => {
    Object.defineProperty(document.documentElement, "clientHeight", {
      configurable: true,
      value: 900,
    });
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      value: 800,
    });
    expect(measureLayoutHeight()).toBe(900);
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

  function stubViewport(height: number, offsetTop = 0) {
    const vv = {
      height,
      offsetTop,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      value: vv,
    });
    return vv;
  }

  function stubMatchMedia(standalone: boolean) {
    window.matchMedia = ((query: string) => ({
      matches: query.includes("standalone") ? standalone : false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
    })) as typeof window.matchMedia;
  }

  it("does nothing in a mobile browser tab", () => {
    stubMatchMedia(false);
    stubViewport(500, 0);
    renderHook(() => useKeyboardOffset());
    expect(
      document.documentElement.style.getPropertyValue("--keyboard-offset"),
    ).toBe("");
  });

  it("sets --keyboard-offset in PWA when a soft keyboard is open", () => {
    stubMatchMedia(true);
    Object.defineProperty(document.documentElement, "clientHeight", {
      configurable: true,
      value: 844,
    });
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      value: 844,
    });
    stubViewport(500, 0);

    renderHook(() => useKeyboardOffset());

    expect(
      document.documentElement.style.getPropertyValue("--keyboard-offset"),
    ).toBe("344px");
  });
});
