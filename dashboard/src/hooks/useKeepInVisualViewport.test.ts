import { afterEach, describe, expect, it } from "vitest";
import {
  measureVisualViewportOverflow,
  needsComposerVisualViewportFix,
} from "./viewport";

describe("measureVisualViewportOverflow", () => {
  it("is zero when the box ends inside the visual viewport", () => {
    expect(
      measureVisualViewportOverflow(700, { height: 700, offsetTop: 0 }),
    ).toBe(0);
    expect(
      measureVisualViewportOverflow(680, { height: 700, offsetTop: 0 }),
    ).toBe(0);
  });

  it("reports how far the box extends past the visual viewport", () => {
    expect(
      measureVisualViewportOverflow(900, { height: 700, offsetTop: 0 }),
    ).toBe(200);
    expect(
      measureVisualViewportOverflow(900, { height: 600, offsetTop: 100 }),
    ).toBe(200);
  });
});

describe("needsComposerVisualViewportFix", () => {
  const originalMatchMedia = window.matchMedia;
  const originalUa = navigator.userAgent;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value: originalUa,
    });
  });

  it("is true on narrow viewports", () => {
    window.matchMedia = ((query: string) => ({
      matches: query.includes("767px"),
      media: query,
      addEventListener() {},
      removeEventListener() {},
    })) as typeof window.matchMedia;
    expect(needsComposerVisualViewportFix()).toBe(true);
  });

  it("is true for Android Chrome desktop-site (wide layout)", () => {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
    })) as typeof window.matchMedia;
    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value:
        "Mozilla/5.0 (Linux; Android 14; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    });
    expect(needsComposerVisualViewportFix()).toBe(true);
  });
});
