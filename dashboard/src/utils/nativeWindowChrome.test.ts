import { afterEach, describe, expect, it, vi } from "vitest";

const loadAppearanceOnBoot = vi.hoisted(() => vi.fn());

vi.mock("../styles/appearanceStorage", () => ({ loadAppearanceOnBoot }));

import {
  applyNativeWindowChrome,
  bootNativeWindowChrome,
} from "./nativeWindowChrome";

type BridgeHost = Window & { octopDesktop?: unknown };

function stubBridge(): ReturnType<typeof vi.fn> {
  const setWindowChrome = vi.fn();
  Object.defineProperty(window, "octopDesktop", {
    configurable: true,
    value: { setWindowChrome },
  });
  return setWindowChrome;
}

afterEach(() => {
  delete (window as BridgeHost).octopDesktop;
  loadAppearanceOnBoot.mockReset();
});

describe("nativeWindowChrome", () => {
  it("reports the stored preference and its resolved mode before first paint", () => {
    const setWindowChrome = stubBridge();
    loadAppearanceOnBoot.mockReturnValue({ preference: "system" });

    bootNativeWindowChrome(true);

    expect(setWindowChrome).toHaveBeenCalledWith({
      mode: "dark",
      scheme: "system",
    });
  });

  it("keeps an explicit preference instead of the OS answer", () => {
    const setWindowChrome = stubBridge();
    loadAppearanceOnBoot.mockReturnValue({ preference: "light" });

    bootNativeWindowChrome(true);

    expect(setWindowChrome).toHaveBeenCalledWith({
      mode: "light",
      scheme: "light",
    });
  });

  it("forwards later theme changes from the hook path", () => {
    const setWindowChrome = stubBridge();

    applyNativeWindowChrome("dark", "dark");

    expect(setWindowChrome).toHaveBeenCalledWith({
      mode: "dark",
      scheme: "dark",
    });
  });

  it("is a no-op in the browser, where there is no native chrome", () => {
    expect(() => bootNativeWindowChrome(false)).not.toThrow();
    expect(() => applyNativeWindowChrome("dark", "dark")).not.toThrow();
  });
});
